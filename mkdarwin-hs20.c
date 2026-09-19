#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <stdarg.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

#define UUID_LEN 37
#define MAX_ROOTS 16

struct root_cert {
  char pem_path[PATH_MAX];
  char der_path[PATH_MAX];
  char uuid[UUID_LEN];
};

static void die(const char *fmt, ...)
{
  va_list ap;

  fprintf(stderr, "mkdarwin-hs20: ");
  va_start(ap, fmt);
  vfprintf(stderr, fmt, ap);
  va_end(ap);
  fputc('\n', stderr);
  exit(1);
}

static void *xmalloc(size_t size)
{
  void *p = malloc(size ? size : 1);

  if (!p)
    die("out of memory");
  return p;
}

static int read_file(const char *path, unsigned char **data, size_t *len)
{
  FILE *fp;
  long size;
  size_t got;
  unsigned char *buf;

  fp = fopen(path, "rb");
  if (!fp)
    return -1;
  if (fseek(fp, 0, SEEK_END) < 0) {
    fclose(fp);
    return -1;
  }
  size = ftell(fp);
  if (size < 0 || fseek(fp, 0, SEEK_SET) < 0) {
    fclose(fp);
    return -1;
  }

  buf = xmalloc((size_t)size + 1);
  got = fread(buf, 1, (size_t)size, fp);
  fclose(fp);
  if (got != (size_t)size) {
    free(buf);
    return -1;
  }

  buf[got] = 0;
  *data = buf;
  *len = got;
  return 0;
}

static int write_file(const char *path, const void *data, size_t len)
{
  FILE *fp;
  size_t written;

  fp = fopen(path, "wb");
  if (!fp)
    return -1;
  written = fwrite(data, 1, len, fp);
  if (fclose(fp) < 0)
    return -1;
  return written == len ? 0 : -1;
}

static int run_openssl(char *const argv[], const char *password,
                       const char *out_path)
{
  pid_t pid;
  int status;
  int fd;

  pid = fork();
  if (pid < 0)
    return -1;
  if (pid == 0) {
    if (out_path) {
      fd = open(out_path, O_WRONLY | O_CREAT | O_TRUNC, 0600);
      if (fd < 0)
        _exit(126);
      if (dup2(fd, STDOUT_FILENO) < 0)
        _exit(126);
      close(fd);
    }
    if (setenv("PFX_PASS", password, 1) < 0)
      _exit(126);
    execvp(argv[0], argv);
    _exit(127);
  }

  while (waitpid(pid, &status, 0) < 0) {
    if (errno != EINTR)
      return -1;
  }
  if (!WIFEXITED(status))
    return -1;
  return WEXITSTATUS(status) == 0 ? 0 : -1;
}

static void uuid(char out[UUID_LEN])
{
  unsigned char data[16];
  int fd;
  ssize_t got;

  fd = open("/dev/urandom", O_RDONLY);
  if (fd < 0)
    die("cannot open /dev/urandom: %s", strerror(errno));
  got = read(fd, data, sizeof(data));
  close(fd);
  if (got != (ssize_t)sizeof(data))
    die("cannot read /dev/urandom");

  data[6] = (data[6] & 0x0f) | 0x40;
  data[8] = (data[8] & 0x3f) | 0x80;
  snprintf(out, UUID_LEN,
           "%02X%02X%02X%02X-%02X%02X-%02X%02X-%02X%02X-%02X%02X%02X%02X%02X%02X",
           data[0], data[1], data[2], data[3], data[4], data[5], data[6],
           data[7], data[8], data[9], data[10], data[11], data[12], data[13],
           data[14], data[15]);
}

static void xml_text(FILE *fp, const char *s)
{
  for (; *s; s++) {
    switch (*s) {
    case '&':
      fputs("&amp;", fp);
      break;
    case '<':
      fputs("&lt;", fp);
      break;
    case '>':
      fputs("&gt;", fp);
      break;
    case '\"':
      fputs("&quot;", fp);
      break;
    case '\'':
      fputs("&apos;", fp);
      break;
    default:
      fputc(*s, fp);
      break;
    }
  }
}

static void xml_key(FILE *fp, const char *key)
{
  fputs("<key>", fp);
  xml_text(fp, key);
  fputs("</key>", fp);
}

static void xml_string(FILE *fp, const char *value)
{
  fputs("<string>", fp);
  xml_text(fp, value);
  fputs("</string>", fp);
}

static void xml_key_string(FILE *fp, const char *key, const char *value)
{
  xml_key(fp, key);
  xml_string(fp, value);
}

static void xml_key_bool(FILE *fp, const char *key, bool value)
{
  xml_key(fp, key);
  fputs(value ? "<true/>" : "<false/>", fp);
}

static void xml_key_int(FILE *fp, const char *key, int value)
{
  xml_key(fp, key);
  fprintf(fp, "<integer>%d</integer>", value);
}

static void b64_write(FILE *fp, const unsigned char *data, size_t len)
{
  static const char table[] =
      "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
  size_t i;
  int col = 0;

  for (i = 0; i < len; i += 3) {
    unsigned int value = (unsigned int)data[i] << 16;
    int count = (int)(len - i >= 3 ? 3 : len - i);

    if (count > 1)
      value |= (unsigned int)data[i + 1] << 8;
    if (count > 2)
      value |= data[i + 2];

    fputc(table[(value >> 18) & 63], fp);
    fputc(table[(value >> 12) & 63], fp);
    fputc(count > 1 ? table[(value >> 6) & 63] : '=', fp);
    fputc(count > 2 ? table[value & 63] : '=', fp);
    col += 4;
    if (col == 76) {
      fputc('\n', fp);
      col = 0;
    }
  }
  if (col)
    fputc('\n', fp);
}

static void xml_data(FILE *fp, const unsigned char *data, size_t len)
{
  fputs("<data>\n", fp);
  b64_write(fp, data, len);
  fputs("</data>", fp);
}

static const char *base_name(const char *path)
{
  const char *slash = strrchr(path, '/');

  return slash ? slash + 1 : path;
}

static void safe_name(char *out, size_t out_len, const char *name)
{
  size_t i;
  size_t pos = 0;

  for (i = 0; name[i] && pos + 1 < out_len; i++) {
    unsigned char c = (unsigned char)name[i];

    if ((c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') ||
        (c >= '0' && c <= '9') || c == '.' || c == '_' || c == '-')
      out[pos++] = (char)c;
    else
      out[pos++] = '_';
  }
  while (pos && (out[pos - 1] == '.' || out[pos - 1] == '_'))
    pos--;
  if (!pos) {
    memcpy(out, "passpoint", 9);
    pos = 9;
  }
  out[pos] = 0;
}

static bool is_root_cert(const char *path, const char *info_path)
{
  unsigned char *data;
  size_t len;
  char *line1;
  char *line2;
  char *newline;
  char *subject;
  char *issuer;
  char *end;
  char *argv[] = {
      "openssl", "x509", "-in", (char *)path, "-noout", "-subject",
      "-issuer", "-nameopt", "RFC2253", NULL
  };

  if (run_openssl(argv, "", info_path) < 0)
    return false;
  if (read_file(info_path, &data, &len) < 0)
    return false;

  line1 = (char *)data;
  newline = strchr(line1, '\n');
  if (!newline) {
    free(data);
    return false;
  }
  *newline = 0;
  line2 = newline + 1;
  end = strchr(line2, '\n');
  if (end)
    *end = 0;
  if (strncmp(line1, "subject=", 8) || strncmp(line2, "issuer=", 7)) {
    free(data);
    return false;
  }

  subject = line1 + 8;
  issuer = line2 + 7;
  if (strcmp(subject, issuer)) {
    free(data);
    return false;
  }
  free(data);
  return true;
}

static int extract_roots(const char *ca_path, const char *tmp_dir,
                         struct root_cert *roots, int max_roots,
                         const char *password)
{
  static const char begin[] = "-----BEGIN CERTIFICATE-----";
  static const char end[] = "-----END CERTIFICATE-----";
  unsigned char *data;
  size_t len;
  const char *pos;
  int count = 0;
  char info_path[PATH_MAX];
  char *argv[10];

  if (read_file(ca_path, &data, &len) < 0)
    die("cannot read extracted CA certificates");

  pos = (const char *)data;
  while (pos < (const char *)data + len) {
    const char *start = strstr(pos, begin);
    const char *finish;
    size_t cert_len;

    if (!start)
      break;
    finish = strstr(start + sizeof(begin) - 1, end);
    if (!finish)
      break;
    finish += sizeof(end) - 1;
    cert_len = (size_t)(finish - start);
    if (count >= max_roots)
      die("too many root certificates");

    snprintf(roots[count].pem_path, sizeof(roots[count].pem_path),
             "%s/root-%d.pem", tmp_dir, count);
    if (write_file(roots[count].pem_path, start, cert_len) < 0)
      die("cannot write temporary certificate");

    snprintf(info_path, sizeof(info_path), "%s/info-%d.txt", tmp_dir, count);
    argv[0] = "openssl";
    argv[1] = "x509";
    argv[2] = "-in";
    argv[3] = roots[count].pem_path;
    argv[4] = "-noout";
    argv[5] = "-subject";
    argv[6] = "-issuer";
    argv[7] = "-nameopt";
    argv[8] = "RFC2253";
    argv[9] = NULL;
    if (is_root_cert(roots[count].pem_path, info_path)) {
      snprintf(roots[count].der_path, sizeof(roots[count].der_path),
               "%s/root-%d.der", tmp_dir, count);
      argv[0] = "openssl";
      argv[1] = "x509";
      argv[2] = "-in";
      argv[3] = roots[count].pem_path;
      argv[4] = "-outform";
      argv[5] = "DER";
      argv[6] = NULL;
      if (run_openssl(argv, password, roots[count].der_path) < 0)
        die("cannot convert root certificate to DER");
      uuid(roots[count].uuid);
      count++;
    }
    pos = finish;
  }

  free(data);
  return count;
}

static void write_identity(FILE *fp, const char *pfx_name, const char *password,
                           const char *ident_uuid, const unsigned char *pfx,
                           size_t pfx_len)
{
  fputs("<dict>", fp);
  xml_key_string(fp, "PayloadType", "com.apple.security.pkcs12");
  xml_key_int(fp, "PayloadVersion", 1);
  xml_key(fp, "PayloadIdentifier");
  fputs("<string>local.mkprofile.identity.", fp);
  xml_text(fp, ident_uuid);
  fputs("</string>", fp);
  xml_key(fp, "PayloadUUID");
  xml_string(fp, ident_uuid);
  xml_key_string(fp, "PayloadDisplayName", "Passpoint EAP-TLS Identity");
  xml_key_string(fp, "PayloadCertificateFileName", pfx_name);
  xml_key(fp, "PayloadContent");
  xml_data(fp, pfx, pfx_len);
  xml_key(fp, "Password");
  xml_string(fp, password);
  fputs("</dict>", fp);
}

static void write_root(FILE *fp, const struct root_cert *root, int number,
                       const unsigned char *der, size_t der_len)
{
  char display[64];

  snprintf(display, sizeof(display), "Passpoint Root CA %d", number);
  fputs("<dict>", fp);
  xml_key_string(fp, "PayloadType", "com.apple.security.root");
  xml_key_int(fp, "PayloadVersion", 1);
  xml_key(fp, "PayloadIdentifier");
  fputs("<string>local.mkprofile.ca.", fp);
  xml_text(fp, root->uuid);
  fputs("</string>", fp);
  xml_key(fp, "PayloadUUID");
  xml_string(fp, root->uuid);
  xml_key(fp, "PayloadDisplayName");
  xml_string(fp, display);
  xml_key(fp, "PayloadContent");
  xml_data(fp, der, der_len);
  fputs("</dict>", fp);
}

static void write_uuid_array(FILE *fp, const char *key,
                             const struct root_cert *roots, int root_count)
{
  int i;

  xml_key(fp, key);
  fputs("<array>", fp);
  for (i = 0; i < root_count; i++)
    xml_string(fp, roots[i].uuid);
  fputs("</array>", fp);
}

static void write_string_array(FILE *fp, const char *key, const char *value)
{
  xml_key(fp, key);
  fputs("<array>", fp);
  xml_string(fp, value);
  fputs("</array>", fp);
}

static void write_wifi(FILE *fp, const char *friendly_name, const char *fqdn,
                       const char *realm, const char *wifi_uuid,
                       const char *ident_uuid, const struct root_cert *roots,
                       int root_count)
{
  fputs("<dict>", fp);
  xml_key_string(fp, "PayloadType", "com.apple.wifi.managed");
  xml_key_int(fp, "PayloadVersion", 1);
  xml_key(fp, "PayloadIdentifier");
  fputs("<string>local.mkprofile.passpoint.", fp);
  xml_text(fp, wifi_uuid);
  fputs("</string>", fp);
  xml_key(fp, "PayloadUUID");
  xml_string(fp, wifi_uuid);
  xml_key(fp, "PayloadDisplayName");
  xml_string(fp, friendly_name);
  xml_key_bool(fp, "AutoJoin", true);
  xml_key_string(fp, "EncryptionType", "WPA");
  xml_key_bool(fp, "IsHotspot", true);
  xml_key_string(fp, "PayloadCertificateUUID", ident_uuid);
  xml_key(fp, "DisplayedOperatorName");
  xml_string(fp, friendly_name);
  xml_key(fp, "DomainName");
  xml_string(fp, fqdn);
  write_string_array(fp, "NAIRealmNames", realm);
  xml_key(fp, "EAPClientConfiguration");
  fputs("<dict>", fp);
  xml_key(fp, "AcceptEAPTypes");
  fputs("<array><integer>13</integer></array>", fp);
  xml_key_bool(fp, "TLSCertificateIsRequired", true);
  xml_key_bool(fp, "TLSAllowTrustExceptions", false);
  write_uuid_array(fp, "PayloadCertificateAnchorUUID", roots, root_count);
  fputs("</dict></dict>", fp);
}

static void write_profile(const char *out_path, const char *friendly_name,
                          const char *fqdn, const char *realm,
                          const char *password, const char *pfx_path,
                          const unsigned char *pfx, size_t pfx_len,
                          struct root_cert *roots, int root_count)
{
  FILE *fp;
  int i;
  char ident_uuid[UUID_LEN];
  char wifi_uuid[UUID_LEN];
  char profile_uuid[UUID_LEN];

  uuid(ident_uuid);
  uuid(wifi_uuid);
  uuid(profile_uuid);

  fp = fopen(out_path, "wb");
  if (!fp)
    die("cannot create %s: %s", out_path, strerror(errno));

  fputs("<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n", fp);
  fputs("<!DOCTYPE plist PUBLIC \"-//Apple//DTD PLIST 1.0//EN\" "
        "\"http://www.apple.com/DTDs/PropertyList-1.0.dtd\">\n",
        fp);
  fputs("<plist version=\"1.0\"><dict>", fp);
  xml_key_string(fp, "PayloadType", "Configuration");
  xml_key_int(fp, "PayloadVersion", 1);
  xml_key(fp, "PayloadIdentifier");
  fputs("<string>local.mkprofile.profile.", fp);
  xml_text(fp, profile_uuid);
  fputs("</string>", fp);
  xml_key(fp, "PayloadUUID");
  xml_string(fp, profile_uuid);
  xml_key(fp, "PayloadDisplayName");
  fputs("<string>Passpoint ", fp);
  xml_text(fp, friendly_name);
  fputs("</string>", fp);
  xml_key(fp, "PayloadDescription");
  fputs("<string>HS20 EAP-TLS profile for ", fp);
  xml_text(fp, fqdn);
  fputs("</string>", fp);
  xml_key_bool(fp, "PayloadRemovalDisallowed", false);
  xml_key(fp, "PayloadContent");
  fputs("<array>", fp);

  write_identity(fp, base_name(pfx_path), password, ident_uuid, pfx, pfx_len);
  for (i = 0; i < root_count; i++) {
    unsigned char *der;
    size_t der_len;

    if (read_file(roots[i].der_path, &der, &der_len) < 0)
      die("cannot read root certificate");
    write_root(fp, &roots[i], i + 1, der, der_len);
    free(der);
  }
  write_wifi(fp, friendly_name, fqdn, realm, wifi_uuid, ident_uuid, roots,
             root_count);
  fputs("</array></dict></plist>\n", fp);
  if (fclose(fp) < 0)
    die("cannot finish %s", out_path);
}

static void cleanup_tmp(const char *tmp_dir, struct root_cert *roots,
                        int root_count)
{
  int i;
  char path[PATH_MAX];

  snprintf(path, sizeof(path), "%s/client.pem", tmp_dir);
  unlink(path);
  snprintf(path, sizeof(path), "%s/client.key", tmp_dir);
  unlink(path);
  snprintf(path, sizeof(path), "%s/ca.pem", tmp_dir);
  unlink(path);
  for (i = 0; i < root_count; i++) {
    unlink(roots[i].pem_path);
    unlink(roots[i].der_path);
    snprintf(path, sizeof(path), "%s/info-%d.txt", tmp_dir, i);
    unlink(path);
  }
  rmdir(tmp_dir);
}

int main(int argc, char **argv)
{
  char *password;
  char tmp_template[] = "/tmp/mkdarwin-hs20.XXXXXX";
  char ca_path[PATH_MAX];
  char client_path[PATH_MAX];
  char key_path[PATH_MAX];
  char out_name[PATH_MAX];
  char tmp_dir[PATH_MAX];
  unsigned char *pfx;
  unsigned char *data;
  size_t pfx_len;
  size_t data_len;
  struct root_cert roots[MAX_ROOTS] = {0};
  int root_count;
  int output_len;
  size_t output_used;
  char *client_argv[10];
  char *key_argv[10];
  char *ca_argv[10];

  if (argc != 5)
    die("usage: %s FRIENDLY_NAME FQDN REALM client.pfx", argv[0]);
  if (!argv[1][0] || !argv[2][0] || !argv[3][0])
    die("friendly name, FQDN and realm must not be empty");
  if (access(argv[4], R_OK) < 0)
    die("%s: %s", argv[4], strerror(errno));

  password = getpass("PFX password: ");
  if (!password)
    die("cannot read PFX password");

  if (!mkdtemp(tmp_template))
    die("cannot create temporary directory: %s", strerror(errno));
  snprintf(tmp_dir, sizeof(tmp_dir), "%s", tmp_template);
  snprintf(ca_path, sizeof(ca_path), "%s/ca.pem", tmp_dir);
  snprintf(client_path, sizeof(client_path), "%s/client.pem", tmp_dir);
  snprintf(key_path, sizeof(key_path), "%s/client.key", tmp_dir);

  client_argv[0] = "openssl";
  client_argv[1] = "pkcs12";
  client_argv[2] = "-in";
  client_argv[3] = argv[4];
  client_argv[4] = "-clcerts";
  client_argv[5] = "-nokeys";
  client_argv[6] = "-passin";
  client_argv[7] = "env:PFX_PASS";
  client_argv[8] = NULL;
  if (run_openssl(client_argv, password, client_path) < 0)
    die("cannot read client certificate from PFX");

  key_argv[0] = "openssl";
  key_argv[1] = "pkcs12";
  key_argv[2] = "-in";
  key_argv[3] = argv[4];
  key_argv[4] = "-nocerts";
  key_argv[5] = "-nodes";
  key_argv[6] = "-passin";
  key_argv[7] = "env:PFX_PASS";
  key_argv[8] = NULL;
  if (run_openssl(key_argv, password, key_path) < 0)
    die("cannot read private key from PFX");

  if (read_file(client_path, &data, &data_len) < 0 ||
      !strstr((char *)data, "-----BEGIN CERTIFICATE-----"))
    die("PFX has no client certificate");
  free(data);
  if (read_file(key_path, &data, &data_len) < 0 ||
      !strstr((char *)data, "PRIVATE KEY-----"))
    die("PFX has no private key");
  free(data);

  ca_argv[0] = "openssl";
  ca_argv[1] = "pkcs12";
  ca_argv[2] = "-in";
  ca_argv[3] = argv[4];
  ca_argv[4] = "-cacerts";
  ca_argv[5] = "-nokeys";
  ca_argv[6] = "-passin";
  ca_argv[7] = "env:PFX_PASS";
  ca_argv[8] = NULL;
  if (run_openssl(ca_argv, password, ca_path) < 0)
    die("PFX has no readable CA certificates");

  root_count = extract_roots(ca_path, tmp_dir, roots, MAX_ROOTS, password);
  if (!root_count)
    die("PFX CA chain has no self-signed root certificate");
  if (read_file(argv[4], &pfx, &pfx_len) < 0)
    die("cannot read %s", argv[4]);

  safe_name(out_name, sizeof(out_name), argv[1]);
  output_used = strlen(out_name);
  output_len = snprintf(out_name + output_used, sizeof(out_name) - output_used,
                        "-hs20.mobileconfig");
  if (output_len < 0 || (size_t)output_len >= sizeof(out_name) - output_used)
    die("output filename is too long");
  write_profile(out_name, argv[1], argv[2], argv[3], password, argv[4], pfx,
                pfx_len, roots, root_count);
  free(pfx);
  cleanup_tmp(tmp_dir, roots, root_count);
  memset(password, 0, strlen(password));
  printf("%s\n", out_name);
  return 0;
}
