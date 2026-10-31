package main

import (
	"archive/tar"
	"bytes"
	"compress/gzip"
	"context"
	"crypto/tls"
	"crypto/x509"
	"encoding/json"
	"encoding/pem"
	"fmt"
	"io"
	"os"
	"strings"
	"time"
)

var certNames = []string{"cacert.pem", "cakey.pem", "cert.pem", "key.pem", "cacert_gen.pem", "cakey_gen.pem", "cert_gen.pem", "key_gen.pem"}

const privateState = "/work/build/native-lifecycle-private"

func certFiles() map[string][]byte {
	files := map[string][]byte{}
	for _, name := range certNames {
		files[name] = nrRead("/etc/" + name)
	}
	return files
}
func certArchiveMatches(files map[string][]byte) {
	certArchiveMatchesData(nrRead("/jffs/cert.tgz"), files)
}
func certArchiveMatchesData(data []byte, files map[string][]byte) {
	z, e := gzip.NewReader(bytes.NewReader(data))
	nrMust(e)
	defer z.Close()
	t := tar.NewReader(z)
	count := 0
	for {
		h, e := t.Next()
		if e == io.EOF {
			break
		}
		nrMust(e)
		name := strings.TrimPrefix(h.Name, "etc/")
		expected, ok := files[name]
		if !ok || h.Typeflag != tar.TypeReg && h.Typeflag != tar.TypeRegA {
			panic("unexpected certificate archive member: " + h.Name)
		}
		b, e := io.ReadAll(t)
		nrMust(e)
		if !bytes.Equal(b, expected) {
			panic("saved certificate bytes differ: " + name)
		}
		count++
	}
	if count != len(certNames) {
		panic("certificate archive is incomplete")
	}
}
func certMatch(files map[string][]byte) {
	for _, name := range certNames {
		if !bytes.Equal(files[name], nrRead("/etc/"+name)) {
			panic("certificate changed: " + name)
		}
	}
}
func certValid() {
	_, e := tls.X509KeyPair(nrRead("/etc/cert.pem"), nrRead("/etc/key.pem"))
	nrMust(e)
	for _, name := range []string{"key.pem", "cakey.pem", "key_gen.pem", "cakey_gen.pem"} {
		info, e := os.Stat("/etc/" + name)
		nrMust(e)
		if info.Mode().Perm()&0077 != 0 {
			panic("private key is accessible to other guest users: " + name)
		}
	}
	roots := x509.NewCertPool()
	if !roots.AppendCertsFromPEM(nrRead("/etc/cacert.pem")) {
		panic("CA parse")
	}
	block, _ := pem.Decode(nrRead("/etc/cert.pem"))
	leaf, e := x509.ParseCertificate(block.Bytes)
	nrMust(e)
	_, e = leaf.Verify(x509.VerifyOptions{Roots: roots, DNSName: "192.168.77.1"})
	nrMust(e)
}
func certClear() {
	for _, name := range append(append([]string{}, certNames...), "cert.crt", "server.pem") {
		nrMust(os.RemoveAll("/etc/" + name))
	}
	os.Remove("/tmp/native-openssl-invocations")
}
func certNoGeneration() {
	if b, _ := os.ReadFile("/tmp/native-openssl-invocations"); len(b) != 0 {
		panic("unexpected openssl regeneration: " + string(b))
	}
}
func main() {
	if len(os.Args) != 2 {
		panic("generate or restore phase required")
	}
	phase := os.Args[1]
	ctx, cancel := context.WithTimeout(context.Background(), 150*time.Second)
	defer cancel()
	checks := []string{}
	details := map[string]any{}
	if phase == "generate" {
		nrMust(os.MkdirAll(privateState, 0700))
		nrMust(os.Chmod(privateState, 0700))
		s := nrStart(ctx, "cert-generate", true)
		defer s.stop()
		certValid()
		files := certFiles()
		certArchiveMatches(files)
		if len(nrRead("/tmp/native-openssl-invocations")) == 0 {
			panic("original openssl generation was not exercised")
		}
		checks = append(checks, "native_auto_generated_ca_server_key_and_verified_tls", "native_save_cert_archive_contains_all_eight_exact_files")
		fingerprint := s.fingerprint
		details["generated_leaf_sha256"] = fingerprint
		s.stop()
		os.Remove("/tmp/native-openssl-invocations")
		s = nrStart(ctx, "cert-service-restart", true)
		defer s.stop()
		certMatch(files)
		certNoGeneration()
		if s.fingerprint != fingerprint {
			panic("service restart changed certificate")
		}
		checks = append(checks, "https_process_restart_reuses_existing_certificate")
		s.stop()
		nrMust(os.WriteFile("/etc/key.pem", files["cakey_gen.pem"], 0600))
		s = nrStart(ctx, "cert-key-mismatch", true)
		defer s.stop()
		certMatch(files)
		certNoGeneration()
		certValid()
		checks = append(checks, "native_mismatched_server_key_restores_valid_saved_pair")
		s.stop()
		nrMust(os.WriteFile(privateState+"/cert.tgz", nrRead("/jffs/cert.tgz"), 0600))
		b, e := json.Marshal(map[string]string{"leaf_sha256": fingerprint})
		nrMust(e)
		nrMust(os.WriteFile(privateState+"/expected.json", b, 0600))
	} else if phase == "restore" {
		expected := map[string]string{}
		nrMust(json.Unmarshal(nrRead(privateState+"/expected.json"), &expected))
		for _, name := range certNames {
			if _, e := os.Stat("/etc/" + name); !os.IsNotExist(e) {
				panic("fresh guest unexpectedly has a certificate")
			}
		}
		originalArchive := nrRead(privateState + "/cert.tgz")
		nrMust(os.WriteFile("/jffs/cert.tgz", originalArchive, 0600))
		s := nrStart(ctx, "cert-cold-restore", true)
		defer s.stop()
		certValid()
		certArchiveMatchesData(originalArchive, certFiles())
		certArchiveMatches(certFiles())
		certNoGeneration()
		if s.fingerprint != expected["leaf_sha256"] {
			panic("fresh VM restore changed certificate")
		}
		if target, e := os.Readlink("/etc/cert.crt"); e != nil || !strings.HasSuffix(target, "cacert.pem") {
			panic("CA export link not restored")
		}
		if !bytes.Equal(nrRead("/etc/server.pem"), append(nrRead("/etc/key.pem"), nrRead("/etc/cert.pem")...)) {
			panic("server.pem not reconstructed")
		}
		checks = append(checks, "fresh_vm_native_restore_keeps_leaf_and_complete_key_archive", "native_restore_recreates_export_link_and_combined_pem")
		details["restored_leaf_sha256"] = s.fingerprint
		s.stop()
		certClear()
		nrMust(os.WriteFile("/jffs/cert.tgz", []byte("deliberately-invalid-owned-test-archive"), 0600))
		s = nrStart(ctx, "cert-corrupt-archive", true)
		defer s.stop()
		certValid()
		certArchiveMatches(certFiles())
		if s.fingerprint == expected["leaf_sha256"] {
			panic("invalid archive was reused")
		}
		checks = append(checks, "native_corrupt_archive_regenerates_valid_tls_and_saved_archive")
		s.stop()
		certClear()
		nrMust(os.Remove("/jffs/cert.tgz"))
		nrCommand("/bin/nvram", "set", "https_crt_save=0")
		s = nrStart(ctx, "cert-nosave", true)
		defer s.stop()
		certValid()
		if _, e := os.Stat("/jffs/cert.tgz"); !os.IsNotExist(e) {
			panic("certificate save disabled but archive created")
		}
		checks = append(checks, "native_save_disabled_generates_tls_without_persistent_archive")
		s.stop()
	} else {
		panic("unknown certificate phase")
	}
	nrResult("cert_"+phase, checks, details)
	fmt.Println("PASS original HTTPd/libshared/gencert/OpenSSL executed; synthetic NVRAM and fresh Linux guests, no router or production key")
}
