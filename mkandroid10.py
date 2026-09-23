#!/usr/bin/env python3

import base64
import getpass
import hashlib
import os
import re
import subprocess
import sys
import tempfile
import uuid
from email import policy
from email.parser import BytesParser
from pathlib import Path
from xml.etree import ElementTree as ET

FRIENDLY_NAME = "NETAMS"
FQDN = "wifi.netams.com"
REALM = "netams.com"
OUT = "passpoint.wificonfig"


def die(msg):
    print(f"mkandroid: {msg}", file=sys.stderr)
    sys.exit(1)


def run(cmd, password=None, data=None):
    env = os.environ.copy()
    if password is not None:
        env["PFX_PASS"] = password

    p = subprocess.run(
        cmd,
        input=data,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    if p.returncode:
        err = p.stderr.decode(errors="replace").strip()
        die(err or "command failed: " + " ".join(cmd))
    return p.stdout


def split_pem(data):
    pat = rb"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----"
    return [m.group(0) + b"\n" for m in re.finditer(pat, data, re.S)]


def cert_der(pem):
    return run(["openssl", "x509", "-outform", "DER"], data=pem)


def cert_dn(pem, field):
    out = run([
        "openssl", "x509", "-noout", f"-{field}", "-nameopt", "RFC2253"
    ], data=pem).decode().strip()
    return out.split("=", 1)[1] if "=" in out else out


def cert_cn(pem):
    subject = cert_dn(pem, "subject")
    for part in subject.split(","):
        if part.startswith("CN=") and part[3:]:
            return part[3:]
    die("client certificate subject has no CN")


def cert_sha1(pem):
    return hashlib.sha1(cert_der(pem)).hexdigest()


def cert_sha256(pem):
    return hashlib.sha256(cert_der(pem)).hexdigest()


def cert_is_ca(pem):
    p = subprocess.run(
        ["openssl", "x509", "-noout", "-ext", "basicConstraints"],
        input=pem,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if p.returncode:
        return False
    return "CA:TRUE" in p.stdout.decode(errors="replace")


def cert_verifies(cert, ca):
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        cert_fn = td / "cert.pem"
        ca_fn = td / "ca.pem"
        cert_fn.write_bytes(cert)
        ca_fn.write_bytes(ca)

        cmd = ["openssl", "verify"]
        if cert_sha256(cert) == cert_sha256(ca):
            # A trusted certificate is normally accepted without checking its
            # own signature. Force the self-signature check for graph edges.
            cmd += ["-check_ss_sig"]
        else:
            cmd += ["-partial_chain"]

        cmd += ["-CAfile", str(ca_fn), str(cert_fn)]
        p = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return p.returncode == 0


def cert_self_signed(cert):
    if cert_dn(cert, "subject") != cert_dn(cert, "issuer"):
        return False
    return cert_verifies(cert, cert)


def print_cert_graph(client, cas):
    certs = [("client", client)]
    certs += [(f"ca{i}", ca) for i, ca in enumerate(cas, 1)]

    print("certificate_graph:")
    for name, cert in certs:
        print(
            f"  {name}: sha256={cert_sha256(cert)} "
            f"subject={cert_dn(cert, 'subject')}"
        )

    edges = 0
    for dst_name, dst in certs:
        for src_name, src in certs:
            if not cert_is_ca(src):
                continue
            if not cert_verifies(dst, src):
                continue

            if src_name == dst_name:
                print(f"  {src_name} -> {dst_name} [self-signed]")
            else:
                print(f"  {src_name} -> {dst_name}")
            edges += 1

    if not edges:
        print("  <no verified signing edges>")


def classify_ca(client, cas):
    # Trust anchor is a certificate that really verifies its own signature.
    # Do not infer root/server roles from order, DN equality or "the other CA".
    roots = [ca for ca in cas if cert_self_signed(ca)]
    if len(roots) != 1:
        die(
            "cannot uniquely identify root CA: "
            f"{len(roots)} certificates have a valid self-signature"
        )
    root_ca = roots[0]

    signers = [ca for ca in cas if cert_verifies(client, ca)]
    if len(signers) != 1:
        die(
            "cannot uniquely identify client issuer: "
            f"{len(signers)} certificates verify client.crt"
        )
    client_ca = signers[0]

    if not cert_verifies(client_ca, root_ca):
        die("client issuer is not chained to root CA")

    return client_ca, root_ca


def pubkey_from_cert(cert):
    pem = run(["openssl", "x509", "-pubkey", "-noout"], data=cert)
    return run(["openssl", "pkey", "-pubin", "-outform", "DER"], data=pem)


def pubkey_from_key(key):
    return run(["openssl", "pkey", "-pubout", "-outform", "DER"], data=key)


def node(parent, name, value=None):
    n = ET.SubElement(parent, "Node")
    ET.SubElement(n, "NodeName").text = name
    if value is not None:
        ET.SubElement(n, "Value").text = value
    return n


def make_pps(fingerprint, username):
    root = ET.Element("MgmtTree", {"xmlns": "syncml:dmddf1.2"})
    ET.SubElement(root, "VerDTD").text = "1.2"

    pps = node(root, "PerProviderSubscription")
    rt = ET.SubElement(pps, "RTProperties")
    typ = ET.SubElement(rt, "Type")
    ET.SubElement(typ, "DDFName").text = (
        "urn:wfa:mo:hotspot2dot0-perprovidersubscription:1.0"
    )

    inst = node(pps, "i001")

    home = node(inst, "HomeSP")
    node(home, "FriendlyName", FRIENDLY_NAME)
    node(home, "FQDN", FQDN)

    cred = node(inst, "Credential")
    node(cred, "Username", username)
    node(cred, "Realm", REALM)

    cert = node(cred, "DigitalCertificate")
    node(cert, "CertificateType", "x509v3")
    node(cert, "CertSHA256Fingerprint", fingerprint)

    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def b64_lines(data):
    return base64.encodebytes(data).rstrip(b"\n")


def make_mime(profile, ca_der, p12):
    boundary = "----netams-passpoint-" + uuid.uuid4().hex
    out = bytearray()

    def add(s=b""):
        if isinstance(s, str):
            s = s.encode("ascii")
        out.extend(s)
        out.extend(b"\r\n")

    add(f"Content-Type: multipart/mixed; boundary={boundary}")
    add("Content-Transfer-Encoding: base64")
    add()

    parts = (
        ("application/x-passpoint-profile", profile),
        ("application/x-x509-ca-cert", ca_der),
        ("application/x-pkcs12", p12),
    )

    for ctype, payload in parts:
        add("--" + boundary)
        add("Content-Type: " + ctype)
        add("Content-Transfer-Encoding: base64")
        add()
        add(b64_lines(payload))

    add("--" + boundary + "--")
    return bytes(out)


def validate_container(encoded, profile, ca_der, p12):
    try:
        raw = base64.b64decode(b"".join(encoded.split()), validate=True)
    except Exception as e:
        die(f"internal error: outer base64 invalid: {e}")

    if not raw.startswith(b"Content-Type: multipart/mixed;"):
        die("internal error: decoded file is not multipart/mixed")

    msg = BytesParser(policy=policy.default).parsebytes(raw)
    if msg.get_content_type() != "multipart/mixed":
        die("internal error: bad outer MIME type")
    if msg.get("Content-Transfer-Encoding") != "base64":
        die("internal error: bad outer transfer encoding")

    got = {}
    for part in msg.iter_parts():
        got[part.get_content_type()] = part.get_payload(decode=True)

    want = {
        "application/x-passpoint-profile": profile,
        "application/x-x509-ca-cert": ca_der,
        "application/x-pkcs12": p12,
    }

    for ctype, data in want.items():
        if got.get(ctype) != data:
            die(f"internal error: MIME part mismatch: {ctype}")

    ET.fromstring(got["application/x-passpoint-profile"])


def main():
    if len(sys.argv) != 2:
        die(f"usage: {sys.argv[0]} client.pfx")

    src = Path(sys.argv[1])
    if not src.is_file():
        die(f"{src}: not found")

    password = getpass.getpass("PFX password: ")

    run([
        "openssl", "pkcs12", "-in", str(src), "-info", "-noout",
        "-passin", "env:PFX_PASS",
    ], password)

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        cert_fn = tmp / "client.pem"
        key_fn = tmp / "client.key"
        chain_fn = tmp / "chain.pem"
        p12_fn = tmp / "client.p12"

        client_data = run([
            "openssl", "pkcs12", "-in", str(src), "-clcerts", "-nokeys",
            "-passin", "env:PFX_PASS",
        ], password)
        clients = split_pem(client_data)
        if len(clients) != 1:
            die(f"expected one client certificate, found {len(clients)}")
        client = clients[0]
        cert_fn.write_bytes(client)
        username = cert_cn(client)

        key_data = run([
            "openssl", "pkcs12", "-in", str(src), "-nocerts", "-nodes",
            "-passin", "env:PFX_PASS",
        ], password)
        if b"PRIVATE KEY-----" not in key_data:
            die("PFX does not contain a private key")
        key_fn.write_bytes(key_data)

        if pubkey_from_cert(client) != pubkey_from_key(key_data):
            die("client certificate does not match private key")

        ca_data = run([
            "openssl", "pkcs12", "-in", str(src), "-cacerts", "-nokeys",
            "-passin", "env:PFX_PASS",
        ], password)
        extra = split_pem(ca_data)
        if not extra:
            die("PFX does not contain additional certificates")

        cas = [cert for cert in extra if cert_is_ca(cert)]
        if not cas:
            die("PFX does not contain CA certificates")

        print_cert_graph(client, cas)
        client_ca, root_ca = classify_ca(client, cas)

        # Keep only the actual client issuer in the identity PKCS#12.
        # The verified self-signed root is Android's RADIUS trust anchor.
        chain_fn.write_bytes(client_ca)

        root_ca_der = cert_der(root_ca)
        fingerprint = cert_sha256(client)

        # Android 10 Passpoint parser expects an empty PKCS#12 password.
        # Keep the password empty, but use old PKCS#12 algorithms instead of
        # passwordless/unencrypted bags: 3DES PBE and SHA-1 MAC.
        run([
            "openssl", "pkcs12", "-export",
            "-inkey", str(key_fn),
            "-in", str(cert_fn),
            "-certfile", str(chain_fn),
            "-out", str(p12_fn),
            "-passout", "pass:",
            "-keypbe", "PBE-SHA1-3DES",
            "-certpbe", "PBE-SHA1-3DES",
            "-macalg", "sha1",
            "-iter", "2048",
        ])

        p12 = p12_fn.read_bytes()

        # Fail before writing output if OpenSSL cannot verify/read it with the
        # empty password Android will use.
        run([
            "openssl", "pkcs12", "-in", str(p12_fn),
            "-info", "-noout", "-passin", "pass:",
        ])

        # Extract the client certificate back from the generated Android
        # PKCS#12 and prove that it is byte-for-byte the same certificate
        # identity as in the source PFX.
        inner_data = run([
            "openssl", "pkcs12", "-in", str(p12_fn),
            "-clcerts", "-nokeys", "-passin", "pass:",
        ])
        inner_clients = split_pem(inner_data)
        if len(inner_clients) != 1:
            die(
                "generated PKCS#12 contains "
                f"{len(inner_clients)} client certificates, expected 1"
            )
        inner_client = inner_clients[0]
        inner_fingerprint = cert_sha256(inner_client)
        if inner_fingerprint != fingerprint:
            die(
                "generated PKCS#12 client certificate mismatch: "
                f"source={fingerprint} inner={inner_fingerprint}"
            )

        profile = make_pps(fingerprint, username)
        mime = make_mime(profile, root_ca_der, p12)
        encoded = base64.encodebytes(mime)
        validate_container(encoded, profile, root_ca_der, p12)

    out = Path(OUT)
    out.write_bytes(encoded)

    print(f"output={out}")
    print(f"size={len(encoded)}")
    print(f"fqdn={FQDN}")
    print(f"realm={REALM}")
    print(f"username={username}")
    print(f"source_client_subject={cert_dn(client, 'subject')}")
    print(f"source_client_issuer={cert_dn(client, 'issuer')}")
    print(f"source_client_sha256={fingerprint}")
    print(f"inner_client_subject={cert_dn(inner_client, 'subject')}")
    print(f"inner_client_issuer={cert_dn(inner_client, 'issuer')}")
    print(f"inner_client_sha256={inner_fingerprint}")
    print("client_cert_match=ok")
    print(f"ca_count={len(cas)}")
    for i, ca in enumerate(cas, 1):
        print(f"ca{i}_subject={cert_dn(ca, 'subject')}")
        print(f"ca{i}_issuer={cert_dn(ca, 'issuer')}")
        print(f"ca{i}_sha1={cert_sha1(ca)}")
        print(f"ca{i}_sha256={cert_sha256(ca)}")
    print(f"ignored_non_ca_count={len(extra) - len(cas)}")
    print(f"client_ca_subject={cert_dn(client_ca, 'subject')}")
    print(f"client_ca_sha1={cert_sha1(client_ca)}")
    print(f"client_ca_sha256={cert_sha256(client_ca)}")
    print(f"root_ca_subject={cert_dn(root_ca, 'subject')}")
    print(f"root_ca_sha1={cert_sha1(root_ca)}")
    print(f"root_ca_sha256={cert_sha256(root_ca)}")
    print("ca_classification=client_issuer+root_ca:ok")
    print("outer_base64=ok")
    print("multipart=ok")
    print("pkcs12_empty_password=ok")
    print("pkcs12_pbe=PBE-SHA1-3DES")
    print("pkcs12_mac=sha1")
    print("pkcs12_iter=2048")


if __name__ == "__main__":
    main()
