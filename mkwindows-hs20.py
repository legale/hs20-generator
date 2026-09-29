#!/usr/bin/env python3
import getpass
import hashlib
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from xml.sax.saxutils import escape


def die(msg):
    print(f"mkwindows-hs20: {msg}", file=sys.stderr)
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


def cert_sha1(der_bytes):
    return hashlib.sha1(der_bytes).hexdigest()


def safe_name(name):
    s = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")
    return s or "passpoint"


PROFILE_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<WLANProfile xmlns="https://www.microsoft.com/networking/WLAN/profile/v1"
             xmlns:v4="https://www.microsoft.com/networking/WLAN/profile/v4">
  <name>{name}</name>
  <SSIDConfig>
    <SSID>
      <name>{name}</name>
    </SSID>
  </SSIDConfig>
  <connectionType>ESS</connectionType>
  <connectionMode>auto</connectionMode>
  <autoSwitch>false</autoSwitch>
  <MSM>
    <security>
      <authEncryption>
        <authentication>WPA2</authentication>
        <encryption>AES</encryption>
        <useOneX>true</useOneX>
      </authEncryption>
      <OneX xmlns="https://www.microsoft.com/networking/OneX/v1">
        <EAPConfig>
          <EapHostConfig xmlns="https://www.microsoft.com/provisioning/EapHostConfig">
            <EapMethod>
              <Type xmlns="https://www.microsoft.com/provisioning/EapCommon">13</Type>
              <VendorId xmlns="https://www.microsoft.com/provisioning/EapCommon">0</VendorId>
              <VendorType xmlns="https://www.microsoft.com/provisioning/EapCommon">0</VendorType>
              <AuthorId xmlns="https://www.microsoft.com/provisioning/EapCommon">0</AuthorId>
            </EapMethod>
            <Config>
              <Eap xmlns="https://www.microsoft.com/provisioning/BaseEapConnectionPropertiesV1">
                <Type>13</Type>
                <EapType xmlns="https://www.microsoft.com/provisioning/EapTlsConnectionPropertiesV1">
                  <CredentialsSource>
                    <CertificateStore>
                      <SimpleCertificateSelector>
                        <TrustedRootCA>{thumbprint}</TrustedRootCA>
                      </SimpleCertificateSelector>
                    </CertificateStore>
                  </CredentialsSource>
                  <ServerValidation>
                    <DisableUserPromptForServerValidation>true</DisableUserPromptForServerValidation>
                    <ServerNames></ServerNames>
                    <TrustedRootCA>{thumbprint}</TrustedRootCA>
                  </ServerValidation>
                  <DifferentUsername>false</DifferentUsername>
                  <PerformServerValidation xmlns="https://www.microsoft.com/provisioning/EapTlsConnectionPropertiesV2">true</PerformServerValidation>
                  <AcceptServerName xmlns="https://www.microsoft.com/provisioning/EapTlsConnectionPropertiesV2">false</AcceptServerName>
                </EapType>
              </Eap>
            </Config>
          </EapHostConfig>
        </EAPConfig>
      </OneX>
    </security>
  </MSM>
  <v4:Hotspot2>
    <v4:DomainName>{fqdn}</v4:DomainName>
    <v4:NAIRealm>
      <v4:name>{realm}</v4:name>
    </v4:NAIRealm>
  </v4:Hotspot2>
</WLANProfile>
"""


def make_profile(friendly_name, fqdn, realm, root_thumbprint):
    return PROFILE_XML.format(
        name=escape(friendly_name),
        fqdn=escape(fqdn),
        realm=escape(realm),
        thumbprint=root_thumbprint,
    )


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

    root_der = None
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
                root_der = cert_der(path)
                break

    if root_der is None:
        die("PFX CA chain has no self-signed root certificate")

    root_thumbprint = cert_sha1(root_der)
    base = safe_name(friendly_name)

    # WLAN profile XML
    xml = make_profile(friendly_name, fqdn, realm, root_thumbprint)
    xml_out = Path(f"{base}-hs20.xml")
    xml_out.write_text(xml, encoding="utf-8")

    # Root CA certificate for import into Windows certificate store
    ca_out = Path(f"{base}-hs20-rootca.cer")
    ca_out.write_bytes(root_der)

    print(xml_out)
    print(ca_out)
    print()
    print("Install on Windows:")
    print(f"  1. certutil -addstore Root {ca_out}")
    print(f"  2. certutil -importpfx {pfx.name}")
    print(f"  3. netsh wlan add profile filename={xml_out}")


if __name__ == "__main__":
    main()
