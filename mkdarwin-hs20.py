#!/usr/bin/env python3
import getpass
import os
import plistlib
import re
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

def die(msg):
    print(f"mkdarwin-hs20: {msg}", file=sys.stderr)
    raise SystemExit(1)


def run(cmd, password=None):
    env = os.environ.copy()
    if password is not None:
        env["PFX_PASS"] = password

    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       env=env)
    if p.returncode:
        msg = p.stderr.decode(errors="replace").strip()
        die(msg or f"command failed: {' '.join(cmd)}")
    return p.stdout


def split_pem(data):
    pat = rb"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----"
    return [m.group(0) + b"\n" for m in re.finditer(pat, data, re.S)]


def cert_info(path):
    out = run([
        "openssl", "x509", "-in", str(path), "-noout",
        "-subject", "-issuer", "-nameopt", "RFC2253"
    ]).decode(errors="replace").splitlines()
    if len(out) != 2:
        die(f"cannot read certificate: {path}")

    subject = out[0].removeprefix("subject=").strip()
    issuer = out[1].removeprefix("issuer=").strip()
    return subject, issuer


def cert_cn(path):
    subject, _ = cert_info(path)
    for part in subject.split(","):
        if part.startswith("CN=") and part[3:]:
            return part[3:]
    die(f"client certificate has no CN: {path}")


def cert_der(path):
    return run(["openssl", "x509", "-in", str(path), "-outform", "DER"])


def new_uuid():
    return str(uuid.uuid4()).upper()


def safe_name(name):
    s = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")
    return s or "passpoint"


def main():
    if len(sys.argv) != 5:
        die(f"usage: {sys.argv[0]} FRIENDLY_NAME FQDN REALM client.pfx")

    friendly_name, fqdn, realm = sys.argv[1:4]
    pfx = Path(sys.argv[4])
    if not friendly_name or not fqdn or not realm:
        die("friendly name, FQDN and realm must not be empty")
    if not pfx.is_file():
        die(f"{pfx}: not found")

    password = getpass.getpass("PFX password: ")

    client_pem = run([
        "openssl", "pkcs12", "-in", str(pfx), "-clcerts", "-nokeys",
        "-passin", "env:PFX_PASS"
    ], password)
    if b"-----BEGIN CERTIFICATE-----" not in client_pem:
        die("PFX has no client certificate")

    key_pem = run([
        "openssl", "pkcs12", "-in", str(pfx), "-nocerts", "-nodes",
        "-passin", "env:PFX_PASS"
    ], password)
    if b"PRIVATE KEY-----" not in key_pem:
        die("PFX has no private key")

    ca_pem = run([
        "openssl", "pkcs12", "-in", str(pfx), "-cacerts", "-nokeys",
        "-passin", "env:PFX_PASS"
    ], password)
    ca_certs = split_pem(ca_pem)
    if not ca_certs:
        die("PFX has no CA certificates")

    roots = []
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        client_path = td / "client.pem"
        client_path.write_bytes(client_pem)
        username = cert_cn(client_path)
        for i, pem in enumerate(ca_certs):
            path = td / f"ca-{i}.pem"
            path.write_bytes(pem)
            subject, issuer = cert_info(path)
            if subject == issuer:
                roots.append(cert_der(path))

    if not roots:
        die("PFX CA chain has no self-signed root certificate")

    ident_uuid = new_uuid()
    wifi_uuid = new_uuid()
    profile_uuid = new_uuid()

    payloads = [{
        "PayloadType": "com.apple.security.pkcs12",
        "PayloadVersion": 1,
        "PayloadIdentifier": f"local.mkprofile.identity.{ident_uuid}",
        "PayloadUUID": ident_uuid,
        "PayloadDisplayName": "Passpoint EAP-TLS Identity",
        "PayloadCertificateFileName": pfx.name,
        "PayloadContent": pfx.read_bytes(),
        "Password": password,
    }]

    anchor_uuids = []
    for i, der in enumerate(roots, 1):
        ca_uuid = new_uuid()
        anchor_uuids.append(ca_uuid)
        payloads.append({
            "PayloadType": "com.apple.security.root",
            "PayloadVersion": 1,
            "PayloadIdentifier": f"local.mkprofile.ca.{ca_uuid}",
            "PayloadUUID": ca_uuid,
            "PayloadDisplayName": f"Passpoint Root CA {i}",
            "PayloadContent": der,
        })

    payloads.append({
        "PayloadType": "com.apple.wifi.managed",
        "PayloadVersion": 1,
        "PayloadIdentifier": f"local.mkprofile.passpoint.{wifi_uuid}",
        "PayloadUUID": wifi_uuid,
        "PayloadDisplayName": friendly_name,
        "AutoJoin": True,
        "EncryptionType": "WPA",
        "IsHotspot": True,
        "PayloadCertificateUUID": ident_uuid,
        "DisplayedOperatorName": friendly_name,
        "DomainName": fqdn,
        "NAIRealmNames": [realm],
        "EAPClientConfiguration": {
            "AcceptEAPTypes": [13],
            "UserName": f"{username}@{fqdn}",
            "TLSCertificateIsRequired": True,
            "TLSAllowTrustExceptions": False,
            "PayloadCertificateAnchorUUID": anchor_uuids,
        },
    })

    profile = {
        "PayloadType": "Configuration",
        "PayloadVersion": 1,
        "PayloadIdentifier": f"local.mkprofile.profile.{profile_uuid}",
        "PayloadUUID": profile_uuid,
        "PayloadDisplayName": f"Passpoint {friendly_name}",
        "PayloadDescription": f"HS20 EAP-TLS profile for {fqdn}",
        "PayloadRemovalDisallowed": False,
        "PayloadContent": payloads,
    }

    out = Path(f"{safe_name(friendly_name)}-hs20.mobileconfig")
    with out.open("wb") as f:
        plistlib.dump(profile, f, fmt=plistlib.FMT_XML, sort_keys=False)

    print(out)


if __name__ == "__main__":
    main()
