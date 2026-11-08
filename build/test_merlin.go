package main

import (
	"bytes"
	"context"
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/sha256"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/binary"
	"encoding/json"
	"encoding/pem"
	"fmt"
	"io"
	"math/big"
	"net"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"syscall"
	"time"
)

var merlinChecks = map[string]bool{}
var merlinVersions = map[string]string{}

func mRecord(name string) { merlinChecks[name] = true; fmt.Println("PASS", name) }
func mWrite(path, text string, mode os.FileMode) {
	nrMust(os.MkdirAll(filepath.Dir(path), 0700))
	nrMust(os.WriteFile(path, []byte(text), mode))
}
func mRun(args ...string) (string, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
	defer cancel()
	b, e := exec.CommandContext(ctx, args[0], args[1:]...).CombinedOutput()
	return string(b), e
}
func mOK(args ...string) string {
	b, e := mRun(args...)
	if e != nil {
		panic(fmt.Sprintf("%v: %v\n%s", args, e, b))
	}
	return b
}
func mReject(args ...string) {
	b, e := mRun(args...)
	if e == nil {
		panic(fmt.Sprintf("accepted invalid input %v: %s", args, b))
	}
}

type mProcess struct {
	cmd  *exec.Cmd
	file *os.File
}

func mStart(name string, args ...string) *mProcess {
	f, e := os.Create("/tmp/merlin/" + name + ".log")
	nrMust(e)
	c := exec.Command(args[0], args[1:]...)
	c.Stdout = f
	c.Stderr = f
	nrMust(c.Start())
	return &mProcess{c, f}
}
func (p *mProcess) stop() {
	if p.cmd != nil {
		_ = p.cmd.Process.Signal(syscall.SIGTERM)
		done := make(chan struct{})
		go func() { p.cmd.Wait(); close(done) }()
		select {
		case <-done:
		case <-time.After(3 * time.Second):
			p.cmd.Process.Kill()
			<-done
		}
		p.file.Close()
		p.cmd = nil
	}
}
func mWait(name string, f func() bool) {
	end := time.Now().Add(15 * time.Second)
	for time.Now().Before(end) {
		if f() {
			return
		}
		time.Sleep(80 * time.Millisecond)
	}
	for _, n := range []string{name, "openvpn-server", "openvpn-client", "dropbear", "miniupnpd", "dnsmasq"} {
		if b, e := os.ReadFile("/tmp/merlin/" + n + ".log"); e == nil {
			fmt.Printf("DIAGNOSTIC_%s\n%s\n", n, b)
		}
	}
	panic("readiness failed: " + name)
}

func mVersions() {
	for _, v := range []struct {
		name, path, version string
		args                []string
	}{
		{"openvpn", "/usr/sbin/openvpn", "OpenVPN 2.7.6", []string{"--version"}},
		{"dnsmasq", "/usr/sbin/dnsmasq", "Dnsmasq version 2.93", []string{"--version"}},
		{"curl", "/usr/sbin/curl", "curl 8.17.0", []string{"--version"}},
		{"wget", "/usr/libexec/localmod/wget", "GNU Wget 1.25.0", []string{"--version"}},
		{"dropbear", "/usr/sbin/dropbear", "Dropbear v2026.94", []string{"-V"}},
		{"miniupnpd", "/usr/sbin/miniupnpd", "miniupnpd 2.3.11", []string{"--version"}},
	} {
		args := append([]string{v.path}, v.args...)
		out := mOK(args...)
		if !strings.Contains(out, v.version) {
			panic(out)
		}
		merlinVersions[v.name] = strings.Split(out, "\n")[0]
		mWrite("/jffs/localmod-merlin-disabled", "1", 0600)
		old, oe := mRun(args...)
		original := append([]string{"/usr/libexec/localmod/merlin/vendor/" + map[string]string{"dropbear": "dropbear"}[v.name]}, v.args...)
		if v.name != "dropbear" {
			original[0] = "/usr/libexec/localmod/merlin/vendor/" + v.name
		}
		expected, ee := mRun(original...)
		if old != expected || (oe == nil) != (ee == nil) || strings.Contains(old, v.version) {
			panic("factory fallback mismatch " + v.name + ": " + old + expected)
		}
		nrMust(os.Remove("/jffs/localmod-merlin-disabled"))
	}
	mRecord("six_default_entries_run_requested_versions_and_component_marker_selects_exact_factory_output")
	mWrite("/jffs/localmod-merlin-openvpn-disabled", "1", 0600)
	old, oldErr := mRun("/usr/sbin/openvpn", "--version")
	expected, expectedErr := mRun("/usr/libexec/localmod/merlin/vendor/openvpn", "--version")
	// This exact factory build prints its version with exit status1. Match
	// both its bytes and status rather than imposing the new build's status0.
	if old != expected || (oldErr == nil) != (expectedErr == nil) || !strings.Contains(mOK("/usr/sbin/dnsmasq", "--version"), "2.93") {
		panic("OpenVPN-only fallback affected another component")
	}
	nrMust(os.Remove("/jffs/localmod-merlin-openvpn-disabled"))
	mRecord("openvpn_only_disable_marker_retains_other_new_components")
}

func mDNS(network string) string {
	c, e := net.DialTimeout(network, "127.0.0.1:35353", time.Second)
	if e != nil {
		return ""
	}
	defer c.Close()
	c.SetDeadline(time.Now().Add(time.Second))
	q := []byte{0x12, 0x34, 1, 0, 0, 1, 0, 0, 0, 0, 0, 0, 5, 'o', 'w', 'n', 'e', 'd', 4, 't', 'e', 's', 't', 0, 0, 1, 0, 1}
	if network == "tcp" {
		q = append([]byte{0, byte(len(q))}, q...)
	}
	if _, e = c.Write(q); e != nil {
		return ""
	}
	b := make([]byte, 2048)
	var n int
	if network == "tcp" {
		h := make([]byte, 2)
		if _, e = io.ReadFull(c, h); e != nil {
			return ""
		}
		n = int(binary.BigEndian.Uint16(h))
		if n > len(b) {
			return ""
		}
		_, e = io.ReadFull(c, b[:n])
	} else {
		n, e = c.Read(b)
	}
	if e != nil || n < 16 || b[0] != 0x12 || b[1] != 0x34 || b[3]&15 != 0 || binary.BigEndian.Uint16(b[6:8]) == 0 {
		return ""
	}
	return net.IP(b[n-4 : n]).String()
}
func mDNSChecks(u *onlineUU) {
	mWrite("/tmp/merlin/dns.hosts", "198.51.100.42 owned.test\n", 0644)
	config := "port=35353\nlisten-address=127.0.0.1\nbind-interfaces\nno-resolv\nno-hosts\naddn-hosts=/tmp/merlin/dns.hosts\npid-file=/tmp/merlin/dnsmasq.pid\nlog-facility=-\n"
	mWrite("/tmp/merlin/dnsmasq.conf", config, 0600)
	mOK("/usr/sbin/dnsmasq", "--test", "--conf-file=/tmp/merlin/dnsmasq.conf")
	start := func() *mProcess {
		return mStart("dnsmasq", "/usr/sbin/dnsmasq", "--keep-in-foreground", "--conf-file=/tmp/merlin/dnsmasq.conf")
	}
	p := start()
	defer func() { p.stop() }()
	mWait("dnsmasq", func() bool { return mDNS("udp") == "198.51.100.42" && mDNS("tcp") == "198.51.100.42" })
	for i := 0; i < 25; i++ {
		if mDNS("udp") != "198.51.100.42" || mDNS("tcp") != "198.51.100.42" {
			panic("DNS repeated query")
		}
	}
	mRecord("dnsmasq_real_udp_tcp_queries_and_repeated_connections")
	c, e := net.Dial("tcp", "127.0.0.1:35353")
	nrMust(e)
	c.Write([]byte{0, 30, 0x12})
	c.Close()
	mWrite("/tmp/merlin/dns.hosts", "198.51.100.43 owned.test\n", 0644)
	nrMust(p.cmd.Process.Signal(syscall.SIGHUP))
	mWait("dnsmasq", func() bool { return mDNS("udp") == "198.51.100.43" })
	p.stop()
	p = start()
	mWait("dnsmasq", func() bool { return mDNS("tcp") == "198.51.100.43" })
	coUUAlive(u.pid)
	if string(nrRead("/tmp/merlin/dnsmasq.conf")) != config {
		panic("DNS config changed")
	}
	mRecord("dnsmasq_reload_restart_and_partial_client_disconnect_preserve_config_and_uu")
}

func mDownloads(u *onlineUU) {
	repo := onlineRepository()
	defer repo.server.Close()
	defer repo.bad.Close()
	url := "https://repo.fixture.test:35001/onlineprobe/v1.tar.gz"
	blob := repo.blobs["/onlineprobe/v1.tar.gz"]
	mOK("/usr/sbin/curl", "--noproxy", "*", "--fail", "--max-time", "5", "--cacert", "/tmp/online-repo-ca.pem", "-o", "/tmp/merlin/curl.tar.gz", url)
	mOK("/usr/sbin/wget", "-q", "-O", "/tmp/merlin/wget.tar.gz", url)
	if !bytes.Equal(nrRead("/tmp/merlin/curl.tar.gz"), blob) || !bytes.Equal(nrRead("/tmp/merlin/wget.tar.gz"), blob) {
		panic("TLS download bytes")
	}
	mRecord("curl_wget_actual_verified_https_downloads_match_bytes_with_uu")
	mReject("/usr/sbin/curl", "--noproxy", "*", "--fail", "--max-time", "3", "--cacert", "/tmp/online-repo-ca.pem", "https://bad-name.test:35001/onlineprobe/v1.tar.gz")
	mReject("/usr/sbin/curl", "--noproxy", "*", "--fail", "--max-time", "3", "--cacert", "/tmp/online-repo-ca.pem", "https://repo.fixture.test:35002/onlineprobe/v1.tar.gz")
	mReject("/usr/libexec/localmod/wget", "--ca-certificate=/tmp/online-repo-ca.pem", "-T", "3", "-t", "1", "-O", "/tmp/merlin/reject", "https://bad-name.test:35001/onlineprobe/v1.tar.gz")
	mReject("/usr/libexec/localmod/wget", "--ca-certificate=/tmp/online-repo-ca.pem", "-T", "3", "-t", "1", "-O", "/tmp/merlin/reject", "https://repo.fixture.test:35002/onlineprobe/v1.tar.gz")
	coUUAlive(u.pid)
	mRecord("both_download_clients_reject_wrong_hostname_and_untrusted_ca_without_disabling_tls_verification")
}

func mPublic(path string) string {
	out := mOK("/usr/bin/dropbearkey", "-y", "-f", path)
	for _, s := range strings.Split(out, "\n") {
		if strings.HasPrefix(s, "ssh-") || strings.HasPrefix(s, "ecdsa-") {
			fields := strings.Fields(s)
			if len(fields) < 2 {
				panic(out)
			}
			return fields[0] + " " + fields[1]
		}
	}
	panic(out)
}
func mSSH(u *onlineUU) {
	previousHome := os.Getenv("HOME")
	nrMust(os.Setenv("HOME", "/tmp"))
	defer os.Setenv("HOME", previousHome)
	mWrite("/tmp/.ssh/authorized_keys", "", 0600)
	mOK("/usr/bin/dropbearkey", "-t", "ed25519", "-f", "/tmp/merlin/client.key")
	mOK("/usr/libexec/localmod/merlin/vendor/dropbearkey", "-t", "ed25519", "-f", "/jffs/.ssh/dropbear_ed25519_host_key")
	key := nrRead("/jffs/.ssh/dropbear_ed25519_host_key")
	mWrite("/tmp/.ssh/authorized_keys", mPublic("/tmp/merlin/client.key")+"\n", 0600)
	// Dropbear cli-kex matches its remotehost token, without OpenSSH's
	// nonstandard-port bracket notation. Keep strict verification enabled.
	mWrite("/tmp/.ssh/known_hosts", "127.0.0.1 "+mPublic("/jffs/.ssh/dropbear_ed25519_host_key")+"\n", 0600)
	hostKey := "/jffs/.ssh/dropbear_ed25519_host_key"
	start := func() *mProcess {
		return mStart("dropbear", "/usr/bin/qemu-arm", "-0", "dropbear", "-L", "/", "-E", "LD_PRELOAD=/work/build/native_hw_fixture.so", "/usr/sbin/dropbear", "-F", "-E", "-s", "-W", "65536", "-a", "-p", "127.0.0.1:35322", "-P", "/tmp/merlin/dropbear.pid", "-r", hostKey)
	}
	p := start()
	defer func() { p.stop() }()
	mWait("dropbear", func() bool {
		c, e := net.DialTimeout("tcp", "127.0.0.1:35322", time.Second)
		if e != nil {
			return false
		}
		defer c.Close()
		b := make([]byte, 128)
		c.SetDeadline(time.Now().Add(time.Second))
		n, _ := c.Read(b)
		return strings.HasPrefix(string(b[:n]), "SSH-2.0-dropbear")
	})
	run := func() string {
		return mOK("/usr/bin/dbclient", "-T", "-o", "StrictHostKeyChecking=yes", "-i", "/tmp/merlin/client.key", "-p", "35322", "admin@127.0.0.1", "printf LOCALMOD_SSH_OK; test -z \"$LD_LIBRARY_PATH$LD_PRELOAD\"")
	}
	if !strings.Contains(run(), "LOCALMOD_SSH_OK") {
		panic("SSH command")
	}
	mRecord("dropbear_factory_flags_ed25519_key_auth_and_shell_without_private_library_environment")
	p.stop()
	p = start()
	mWait("dropbear", func() bool {
		out, e := mRun("/usr/bin/dbclient", "-T", "-o", "StrictHostKeyChecking=yes", "-i", "/tmp/merlin/client.key", "-p", "35322", "admin@127.0.0.1", "printf RESTART_OK")
		return e == nil && strings.Contains(out, "RESTART_OK")
	})
	if !bytes.Equal(key, nrRead("/jffs/.ssh/dropbear_ed25519_host_key")) {
		panic("host key changed")
	}
	mOK("/usr/bin/dropbearkey", "-t", "ed25519", "-f", "/tmp/merlin/wrong.key")
	mReject("/usr/bin/dbclient", "-T", "-o", "StrictHostKeyChecking=yes", "-i", "/tmp/merlin/wrong.key", "-p", "35322", "admin@127.0.0.1", "true")
	mWrite("/tmp/.ssh/known_hosts", "127.0.0.1 "+mPublic("/tmp/merlin/wrong.key")+"\n", 0600)
	mReject("/usr/bin/dbclient", "-T", "-o", "StrictHostKeyChecking=yes", "-i", "/tmp/merlin/client.key", "-p", "35322", "admin@127.0.0.1", "true")
	coUUAlive(u.pid)
	mRecord("dropbear_restart_keeps_jffs_host_key_and_rejects_unapproved_client_key_with_uu_alive")
	// The factory boot code also persists RSA and ECDSA host keys. Check
	// their real old binary format, rather than silently regenerating them.
	for _, kind := range []string{"rsa", "ecdsa"} {
		p.stop()
		hostKey = "/jffs/.ssh/dropbear_" + kind + "_host_key"
		// Generating a factory2048-bit RSA key under full-system TCG is
		// setup work, not service readiness. Keep ordinary commands at20s;
		// give this single generation attempt its own bounded90s window.
		began := time.Now()
		keyContext, cancel := context.WithTimeout(context.Background(), 90*time.Second)
		out, err := exec.CommandContext(keyContext, "/usr/libexec/localmod/merlin/vendor/dropbearkey", "-t", kind, "-f", hostKey).CombinedOutput()
		cancel()
		if err != nil {
			panic(fmt.Sprintf("factory %s key fixture generation: %v %s", kind, err, out))
		}
		fmt.Printf("FACTORY_HOSTKEY_FIXTURE kind=%s elapsed=%s attempts=1\n", kind, time.Since(began))
		before := nrRead(hostKey)
		mWrite("/tmp/.ssh/known_hosts", "127.0.0.1 "+mPublic(hostKey)+"\n", 0600)
		p = start()
		mWait("dropbear", func() bool {
			out, e := mRun("/usr/bin/dbclient", "-T", "-o", "StrictHostKeyChecking=yes", "-i", "/tmp/merlin/client.key", "-p", "35322", "admin@127.0.0.1", "printf LEGACY_HOSTKEY_OK")
			return e == nil && strings.Contains(out, "LEGACY_HOSTKEY_OK")
		})
		if !bytes.Equal(before, nrRead(hostKey)) {
			panic("factory " + kind + " host key changed")
		}
		coUUAlive(u.pid)
		mRecord("dropbear_retains_factory_" + kind + "_host_key_format_and_authentication")
	}
}

func mSOAP(client *http.Client, action, fields string) (int, string) {
	body := `<?xml version="1.0"?><s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body><u:` + action + ` xmlns:u="urn:schemas-upnp-org:service:WANIPConnection:1">` + fields + `</u:` + action + `></s:Body></s:Envelope>`
	req, e := http.NewRequest("POST", "http://192.168.77.1:35323/ctl/IPConn", strings.NewReader(body))
	nrMust(e)
	req.Header.Set("SOAPAction", `"urn:schemas-upnp-org:service:WANIPConnection:1#`+action+`"`)
	req.Header.Set("Content-Type", "text/xml; charset=utf-8")
	res, e := client.Do(req)
	nrMust(e)
	defer res.Body.Close()
	b, e := io.ReadAll(res.Body)
	nrMust(e)
	return res.StatusCode, string(b)
}
func mUPnP(u *onlineUU) {
	for _, c := range [][]string{{"-t", "nat", "-N", "VUPNP"}, {"-t", "nat", "-N", "VSERVER"}, {"-N", "FUPNP"}} {
		mOK(append([]string{"/usr/sbin/iptables"}, c...)...)
	}
	cfg := "ext_ifname=wan0\nlistening_ip=192.168.77.1/24\nport=35323\nenable_upnp=yes\nenable_natpmp=yes\nsecure_mode=yes\nupnp_forward_chain=FUPNP\nupnp_nat_chain=VUPNP\nnotify_interval=30\nsystem_uptime=yes\nfriendly_name=owned-fixture\nmodel_name=" + nrFixtureModel() + "\nmodel_description=owned-fixture\nmodel_number=" + nrFixtureModel() + "\nserial=owned\nuuid=3ddcd1d3-2380-45f5-b069-020000000001\nlease_file=/jffs/merlin-fixture/upnp.leases\nallow 45000-45010 192.168.77.0/24 45000-45010\ndeny 0-65535 0.0.0.0/0 0-65535\n"
	mWrite("/tmp/merlin/upnp.conf", cfg, 0600)
	nrMust(os.MkdirAll("/jffs/merlin-fixture", 0700))
	mWrite("/jffs/uu/merlin-coexist-fixture", "owned-persistent-uu", 0600)
	mWrite("/tmp/uu/merlin-coexist-fixture", "owned-temporary-uu", 0600)
	mOK("/usr/bin/dbus", "set", "localmod_merlin_peer=owned-software-center-record")
	dial := &net.Dialer{Timeout: time.Second, LocalAddr: &net.TCPAddr{IP: net.ParseIP("192.168.77.1")}}
	client := &http.Client{Transport: &http.Transport{DialContext: dial.DialContext, DisableKeepAlives: true}, Timeout: 3 * time.Second}
	defer client.CloseIdleConnections()
	start := func(program, name string) *mProcess {
		p := mStart(name, program, "-d", "-f", "/tmp/merlin/upnp.conf", "-P", "/tmp/merlin/miniupnpd.pid")
		mWait(name, func() bool {
			res, e := client.Get("http://192.168.77.1:35323/rootDesc.xml")
			if e != nil {
				return false
			}
			defer res.Body.Close()
			b, _ := io.ReadAll(res.Body)
			return res.StatusCode == 200 && strings.Contains(string(b), "WANIPConnection")
		})
		return p
	}
	fields := "<NewRemoteHost></NewRemoteHost><NewExternalPort>45001</NewExternalPort><NewProtocol>TCP</NewProtocol><NewInternalPort>45001</NewInternalPort><NewInternalClient>192.168.77.1</NewInternalClient><NewEnabled>1</NewEnabled><NewPortMappingDescription>owned-test</NewPortMappingDescription><NewLeaseDuration>120</NewLeaseDuration>"
	selector := os.Getenv("LOCALMOD_MERLIN_PROBE")
	if selector == "upnp-raw" {
		for _, probe := range []struct{ name, extra, reason string }{{"private-wan", "", "Port forwarding is impossible"}, {"missing-postrouting", "ext_allow_private_ipv4=yes\n", "chain UPNP-POSTROUTING not found"}} {
			mWrite("/tmp/merlin/upnp.conf", cfg+probe.extra, 0600)
			p := start("/usr/libexec/localmod/merlin/bin/miniupnpd", "miniupnpd-raw-"+probe.name)
			code, body := mSOAP(client, "AddPortMapping", fields)
			p.stop()
			if code != 500 || !strings.Contains(body, "501") || !strings.Contains(string(nrRead("/tmp/merlin/miniupnpd-raw-"+probe.name+".log")), probe.reason) {
				panic(fmt.Sprintf("upstream control %s: %d %s", probe.name, code, body))
			}
			if probe.name == "missing-postrouting" && !strings.Contains(mOK("/usr/sbin/iptables", "-t", "nat", "-S", "VUPNP"), "45001") {
				panic("expected upstream partial DNAT write was absent")
			}
			// Only the empty, owned model chains are cleared after this deliberate
			// upstream failure; no firmware code performs this broad cleanup.
			mOK("/usr/sbin/iptables", "-t", "nat", "-F", "VUPNP")
			mOK("/usr/sbin/iptables", "-F", "FUPNP")
			mRecord("unadapted_miniupnpd_" + probe.name + "_failure_reproduced")
		}
		coUUAlive(u.pid)
		return
	}
	program := "/usr/sbin/miniupnpd"
	if selector == "upnp-factory" {
		program = "/usr/libexec/localmod/merlin/vendor/miniupnpd"
	}
	p := start(program, "miniupnpd")
	defer func() { p.stop() }()
	code, body := mSOAP(client, "AddPortMapping", fields)
	if code != 200 {
		panic(fmt.Sprintf("UPnP add %d %s", code, body))
	}
	rules := mOK("/usr/sbin/iptables", "-t", "nat", "-S", "VUPNP")
	if !strings.Contains(rules, "45001") {
		panic(rules)
	}
	if program == "/usr/sbin/miniupnpd" {
		adapted := string(nrRead("/tmp/.localmod-merlin/miniupnpd.conf"))
		for _, field := range []string{"ext_allow_private_ipv4=yes", "upnp_nat_postrouting_chain=LOCALMOD_UPNP", "pcp_allow_thirdparty=no"} {
			if !strings.Contains(adapted, field) {
				panic("missing compatibility field: " + field)
			}
		}
		if !strings.Contains(mOK("/usr/sbin/iptables", "-t", "nat", "-S", "LOCALMOD_UPNP"), "45001") {
			panic("new bidirectional rule absent")
		}
	}
	code, body = mSOAP(client, "GetSpecificPortMappingEntry", "<NewRemoteHost></NewRemoteHost><NewExternalPort>45001</NewExternalPort><NewProtocol>TCP</NewProtocol>")
	if code != 200 || !strings.Contains(body, "192.168.77.1") {
		panic(body)
	}
	code, body = mSOAP(client, "AddPortMapping", strings.Replace(fields, "192.168.77.1", "192.168.77.2", 1))
	if code == 200 {
		panic("UPnP secure_mode permitted another client: " + body)
	}
	code, body = mSOAP(client, "DeletePortMapping", "<NewRemoteHost></NewRemoteHost><NewExternalPort>45001</NewExternalPort><NewProtocol>TCP</NewProtocol>")
	if code != 200 {
		panic(body)
	}
	if strings.Contains(mOK("/usr/sbin/iptables", "-t", "nat", "-S", "VUPNP"), "45001") {
		panic("UPnP mapping remains")
	}
	label := "miniupnpd_factory_chain_names_real_soap_mapping_query_delete_and_secure_mode_with_uu"
	if program != "/usr/sbin/miniupnpd" {
		label = "factory_control_private_wan_soap_mapping_query_delete_and_secure_mode"
	}
	mRecord(label)
	if program == "/usr/sbin/miniupnpd" {
		// Model the factory NAT replacement. The real ARM32 restore launcher and
		// retained xtables-multi apply it; the service dependency must return
		// before a subsequent mapping request, independently of custom scripts.
		mWrite("/tmp/merlin/nat.restore", "*nat\n:PREROUTING ACCEPT [0:0]\n:POSTROUTING ACCEPT [0:0]\n:OUTPUT ACCEPT [0:0]\n:VSERVER - [0:0]\n:VUPNP - [0:0]\n-A VSERVER -j VUPNP\n-A POSTROUTING -d 198.51.100.0/24 -j RETURN\nCOMMIT\n", 0600)
		mOK("/bin/nvram", "set", "jffs2_scripts=0")
		mOK("/usr/sbin/iptables-restore", "/tmp/merlin/nat.restore")
		for i := 0; i < 2; i++ {
			mOK("/usr/libexec/localmod/miniupnp-compat", "--firewall")
		}
		post := mOK("/usr/sbin/iptables", "-t", "nat", "-S", "POSTROUTING")
		if strings.Count(post, "-j LOCALMOD_UPNP") != 1 || !strings.Contains(post, "198.51.100.0/24 -j RETURN") {
			panic(post)
		}
		code, body = mSOAP(client, "AddPortMapping", strings.ReplaceAll(fields, "45001", "45002"))
		if code != 200 {
			panic("mapping after factory NAT replacement: " + body)
		}
		code, body = mSOAP(client, "DeletePortMapping", "<NewRemoteHost></NewRemoteHost><NewExternalPort>45002</NewExternalPort><NewProtocol>TCP</NewProtocol>")
		if code != 200 {
			panic(body)
		}
		coPrivateDenied()
		coUUAlive(u.pid)
		mRecord("miniupnpd_postrouting_dependency_recovers_after_factory_nat_restore_without_custom_scripts_or_duplicate_hooks")
		p.stop()
		mWrite("/tmp/merlin/upnp.conf", cfg+"ext_allow_private_ipv4=no\n", 0600)
		p = start(program, "miniupnpd-policy")
		code, body = mSOAP(client, "AddPortMapping", fields)
		if code != 500 || !strings.Contains(body, "501") {
			panic("explicit private WAN policy overridden: " + body)
		}
		if !strings.Contains(string(nrRead("/tmp/.localmod-merlin/miniupnpd.conf")), "ext_allow_private_ipv4=no") {
			panic("explicit policy missing")
		}
		if string(nrRead("/tmp/merlin/upnp.conf")) != cfg+"ext_allow_private_ipv4=no\n" {
			panic("source config modified")
		}
		p.stop()
		mWrite("/tmp/merlin/upnp.conf", cfg, 0600)
		mRecord("miniupnpd_explicit_private_wan_disabled_setting_is_preserved")
	}
	coUUAlive(u.pid)
	if string(nrRead("/tmp/merlin/upnp.conf")) != cfg || string(nrRead("/jffs/uu/merlin-coexist-fixture")) != "owned-persistent-uu" || string(nrRead("/tmp/uu/merlin-coexist-fixture")) != "owned-temporary-uu" {
		panic("UPnP changed config or UU data")
	}
	if !strings.Contains(mOK("/usr/bin/dbus", "get", "localmod_merlin_peer"), "owned-software-center-record") {
		panic("software-center peer changed")
	}
}

func mVPNKey(ca *x509.Certificate, caKey *ecdsa.PrivateKey, name string, usage x509.ExtKeyUsage) {
	k, e := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	nrMust(e)
	c := &x509.Certificate{SerialNumber: big.NewInt(int64(len(name) + 10)), Subject: pkix.Name{CommonName: name}, NotBefore: time.Now().Add(-time.Hour), NotAfter: time.Now().Add(time.Hour), KeyUsage: x509.KeyUsageDigitalSignature, ExtKeyUsage: []x509.ExtKeyUsage{usage}}
	der, e := x509.CreateCertificate(rand.Reader, c, ca, &k.PublicKey, caKey)
	nrMust(e)
	key, e := x509.MarshalECPrivateKey(k)
	nrMust(e)
	mWrite("/tmp/merlin/"+name+".crt", string(pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: der})), 0600)
	mWrite("/tmp/merlin/"+name+".key", string(pem.EncodeToMemory(&pem.Block{Type: "EC PRIVATE KEY", Bytes: key})), 0600)
}
func mIP(args ...string) []string {
	return append([]string{"/lib/ld-musl-aarch64.so.1", "--library-path", "/fixture/lib", "/fixture/ip"}, args...)
}
func mNS(ns string, args ...string) []string {
	return mIP(append([]string{"netns", "exec", ns}, mIP(args...)...)...)
}
func mDHCPClient() {
	c, e := net.ListenUDP("udp4", &net.UDPAddr{Port: 35368})
	nrMust(e)
	defer c.Close()
	packet := func(kind byte, requested, server net.IP) []byte {
		b := make([]byte, 240)
		b[0] = 1
		b[1] = 1
		b[2] = 6
		binary.BigEndian.PutUint32(b[4:8], 0x4d45524c)
		b[10] = 0x80
		copy(b[28:34], []byte{2, 0, 0, 0, 0, 0x50})
		copy(b[236:], []byte{99, 130, 83, 99})
		b = append(b, 53, 1, kind)
		if requested != nil {
			b = append(b, 50, 4)
			b = append(b, requested.To4()...)
			b = append(b, 54, 4)
			b = append(b, server.To4()...)
		}
		return append(b, 55, 3, 1, 3, 6, 255)
	}
	receive := func(kind byte) (net.IP, net.IP) {
		end := time.Now().Add(5 * time.Second)
		for time.Now().Before(end) {
			c.SetReadDeadline(time.Now().Add(time.Second))
			b := make([]byte, 1500)
			n, _, e := c.ReadFromUDP(b)
			if e != nil {
				continue
			}
			b = b[:n]
			if n < 240 || b[0] != 2 || binary.BigEndian.Uint32(b[4:8]) != 0x4d45524c {
				continue
			}
			var got byte
			var server net.IP
			for at := 240; at < len(b); {
				code := b[at]
				at++
				if code == 255 {
					break
				}
				if code == 0 {
					continue
				}
				if at >= len(b) {
					break
				}
				l := int(b[at])
				at++
				if at+l > len(b) {
					break
				}
				if code == 53 && l == 1 {
					got = b[at]
				}
				if code == 54 && l == 4 {
					server = append(net.IP(nil), b[at:at+4]...)
				}
				at += l
			}
			if got == kind && server != nil {
				return append(net.IP(nil), b[16:20]...), server
			}
		}
		panic("DHCP offer/ack timeout")
	}
	_, e = c.WriteToUDP(packet(1, nil, nil), &net.UDPAddr{IP: net.IPv4bcast, Port: 35367})
	nrMust(e)
	address, server := receive(2)
	_, e = c.WriteToUDP(packet(3, address, server), &net.UDPAddr{IP: net.IPv4bcast, Port: 35367})
	nrMust(e)
	ack, _ := receive(5)
	if !ack.Equal(address) {
		panic("DHCP ACK address differs")
	}
	fmt.Println("DHCP_LEASE_ACK", ack.String())
}
func mDHCP(u *onlineUU) {
	mOK(mIP("netns", "add", "merlin-dhcp")...)
	defer func() { mRun(mIP("netns", "del", "merlin-dhcp")...) }()
	mOK(mIP("link", "add", "dhcps0", "type", "veth", "peer", "name", "dhcpc0")...)
	defer func() { mRun(mIP("link", "del", "dhcps0")...) }()
	mOK(mIP("link", "set", "dhcpc0", "netns", "merlin-dhcp")...)
	mOK(mIP("addr", "add", "192.168.78.1/24", "dev", "dhcps0")...)
	mOK(mIP("link", "set", "dhcps0", "up")...)
	mOK(mNS("merlin-dhcp", "addr", "add", "192.168.78.2/24", "dev", "dhcpc0")...)
	mOK(mNS("merlin-dhcp", "link", "set", "dhcpc0", "up")...)
	mOK(mNS("merlin-dhcp", "route", "add", "255.255.255.255/32", "dev", "dhcpc0")...)
	mWrite("/tmp/merlin/dhcp.leases", "", 0644)
	nrMust(os.Chown("/tmp/merlin/dhcp.leases", 65534, 65534))
	mWrite("/tmp/merlin/dhcp.conf", "port=0\ninterface=dhcps0\nbind-interfaces\ndhcp-authoritative\ndhcp-alternate-port=35367,35368\ndhcp-range=192.168.78.100,192.168.78.110,255.255.255.0,2m\ndhcp-leasefile=/tmp/merlin/dhcp.leases\nlog-dhcp\nlog-facility=-\npid-file=/tmp/merlin/dhcp.pid\n", 0644)
	start := func() *mProcess {
		return mStart("dhcp", "/usr/sbin/dnsmasq", "--keep-in-foreground", "--conf-file=/tmp/merlin/dhcp.conf")
	}
	p := start()
	defer func() { p.stop() }()
	mWait("dhcp", func() bool {
		b, _ := os.ReadFile("/tmp/merlin/dhcp.log")
		return bytes.Contains(b, []byte("DHCP, IP range"))
	})
	out := mOK(mIP("netns", "exec", "merlin-dhcp", "/work/build/test-merlin", "dhcp-client")...)
	if !strings.Contains(out, "DHCP_LEASE_ACK 192.168.78.10") {
		panic(out)
	}
	lease := nrRead("/tmp/merlin/dhcp.leases")
	if !bytes.Contains(lease, []byte("02:00:00:00:00:50")) {
		panic(string(lease))
	}
	p.stop()
	p = start()
	mWait("dhcp", func() bool {
		b, _ := os.ReadFile("/tmp/merlin/dhcp.log")
		return bytes.Contains(b, []byte("DHCP, IP range"))
	})
	if !bytes.Equal(lease, nrRead("/tmp/merlin/dhcp.leases")) {
		panic("DHCP lease changed at restart")
	}
	coUUAlive(u.pid)
	mRecord("dnsmasq_real_dhcp_discover_offer_request_ack_and_lease_file_retained_after_restart")
}
func mVPNPKI() {
	key, e := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	nrMust(e)
	ca := &x509.Certificate{SerialNumber: big.NewInt(3), Subject: pkix.Name{CommonName: "owned-vpn-ca"}, NotBefore: time.Now().Add(-time.Hour), NotAfter: time.Now().Add(time.Hour), IsCA: true, BasicConstraintsValid: true, KeyUsage: x509.KeyUsageCertSign | x509.KeyUsageDigitalSignature}
	der, e := x509.CreateCertificate(rand.Reader, ca, ca, &key.PublicKey, key)
	nrMust(e)
	mWrite("/tmp/merlin/vpn-ca.crt", string(pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: der})), 0600)
	mVPNKey(ca, key, "server", x509.ExtKeyUsageServerAuth)
	mVPNKey(ca, key, "client", x509.ExtKeyUsageClientAuth)
}

func mVPN(u *onlineUU) {
	// Put the server in its own namespace so a successful ping cannot use
	// the guest's local routing table instead of the encrypted TUN channel.
	mOK(mIP("netns", "add", "merlin-vpn-server")...)
	defer func() { mRun(mIP("netns", "del", "merlin-vpn-server")...) }()
	mOK(mIP("link", "add", "vpnctl0", "type", "veth", "peer", "name", "vpnctl1")...)
	defer func() { mRun(mIP("link", "del", "vpnctl0")...) }()
	mOK(mIP("link", "set", "vpnctl1", "netns", "merlin-vpn-server")...)
	mOK(mIP("addr", "add", "192.0.2.1/30", "dev", "vpnctl0")...)
	mOK(mIP("link", "set", "vpnctl0", "up")...)
	mOK(mNS("merlin-vpn-server", "addr", "add", "192.0.2.2/30", "dev", "vpnctl1")...)
	mOK(mNS("merlin-vpn-server", "link", "set", "vpnctl1", "up")...)
	mOK(mNS("merlin-vpn-server", "link", "set", "lo", "up")...)
	mVPNPKI()
	common := "proto udp\nca /tmp/merlin/vpn-ca.crt\nverb 3\nauth SHA256\ndata-ciphers AES-256-GCM\npersist-key\npersist-tun\n"
	mWrite("/tmp/merlin/server.ovpn", common+"dev ovpns0\ndev-type tun\nlocal 192.0.2.2\nport 35325\nserver 10.244.0.0 255.255.255.0\ntopology subnet\ncert /tmp/merlin/server.crt\nkey /tmp/merlin/server.key\ndh none\n", 0600)
	mWrite("/tmp/merlin/client.ovpn", common+"client\ndev ovpnc0\ndev-type tun\nremote 192.0.2.2 35325\nnobind\nroute-noexec\nremote-cert-tls server\nverify-x509-name server name\ncert /tmp/merlin/client.crt\nkey /tmp/merlin/client.key\n", 0600)
	server := mStart("openvpn-server", mIP("netns", "exec", "merlin-vpn-server", "/usr/sbin/openvpn", "--config", "/tmp/merlin/server.ovpn")...)
	defer func() { server.stop() }()
	client := mStart("openvpn-client", "/usr/sbin/openvpn", "--config", "/tmp/merlin/client.ovpn")
	defer func() { client.stop() }()
	mWait("openvpn-client", func() bool {
		b, _ := os.ReadFile("/tmp/merlin/openvpn-client.log")
		return bytes.Contains(b, []byte("Initialization Sequence Completed"))
	})
	// Both real tunnel devices exist; send through the client's TUN route to
	// the server endpoint instead of treating the control handshake as traffic.
	mOK("/bin/ping", "-c", "2", "-W", "3", "-I", "ovpnc0", "10.244.0.1")
	if b := string(nrRead("/tmp/merlin/openvpn-client.log")); !strings.Contains(b, "VERIFY OK") {
		panic(b)
	}
	coUUAlive(u.pid)
	mRecord("openvpn_real_mutual_tls_27_handshake_and_tun_ping_with_uu_alive")
	client.stop()
	server.stop()
	// The official UI can enable its retained PAM plugin. Exercise the actual
	// plugin/module/shadow stack rather than replacing password verification.
	passwd := "vpnfixture:x:2000:2000:owned-vpn-account:/tmp:/bin/false\n"
	shadow := "vpnfixture:" + strings.TrimSpace(string(nrRead("/work/build/native_shadow_hash.txt"))) + ":19000:0:99999:7:::\n"
	for path, text := range map[string]string{"/var/passwd": passwd, "/etc/shadow": shadow, "/etc/group": "vpnfixture:x:2000:\n"} {
		f, e := os.OpenFile(path, os.O_APPEND|os.O_WRONLY|os.O_CREATE, 0600)
		nrMust(e)
		_, e = f.WriteString(text)
		nrMust(e)
		nrMust(f.Close())
	}
	mWrite("/etc/passwd.openvpn", passwd, 0600)
	mWrite("/etc/shadow.openvpn", shadow, 0600)
	mWrite("/etc/pam.d/openvpn", "auth required pam_unix.so\n", 0600)
	mWrite("/tmp/merlin/vpn.auth", "vpnfixture\nlocal-test-password\n", 0600)
	mWrite("/tmp/merlin/vpn.wrong.auth", "vpnfixture\nowned-wrong-password\n", 0600)
	serverConfig := string(nrRead("/tmp/merlin/server.ovpn")) + "plugin /usr/lib/openvpn-plugin-auth-pam.so openvpn\n"
	clientConfig := string(nrRead("/tmp/merlin/client.ovpn")) + "auth-user-pass /tmp/merlin/vpn.auth\n"
	mWrite("/tmp/merlin/server.ovpn", serverConfig, 0600)
	mWrite("/tmp/merlin/client.ovpn", clientConfig, 0600)
	server = mStart("openvpn-server", mIP("netns", "exec", "merlin-vpn-server", "/usr/sbin/openvpn", "--config", "/tmp/merlin/server.ovpn")...)
	client = mStart("openvpn-client", "/usr/sbin/openvpn", "--config", "/tmp/merlin/client.ovpn")
	mWait("openvpn-client", func() bool {
		b, _ := os.ReadFile("/tmp/merlin/openvpn-client.log")
		return bytes.Contains(b, []byte("Initialization Sequence Completed"))
	})
	mOK("/bin/ping", "-c", "1", "-W", "3", "-I", "ovpnc0", "10.244.0.1")
	mWrite("/tmp/merlin/wrong-client.ovpn", strings.Replace(strings.Replace(clientConfig, "dev ovpnc0", "dev ovpnc1", 1), "/tmp/merlin/vpn.auth", "/tmp/merlin/vpn.wrong.auth", 1), 0600)
	wrong := mStart("openvpn-wrong-client", "/usr/sbin/openvpn", "--config", "/tmp/merlin/wrong-client.ovpn")
	defer wrong.stop()
	mWait("openvpn-wrong-client", func() bool {
		b, _ := os.ReadFile("/tmp/merlin/openvpn-wrong-client.log")
		return bytes.Contains(b, []byte("AUTH_FAILED"))
	})
	coUUAlive(u.pid)
	mRecord("openvpn_27_retained_factory_pam_plugin_authenticates_valid_account_and_rejects_wrong_password")
}

func mFactoryConfig() {
	// This option is emitted by the retained factory server generator when
	// negotiation is disabled. Establish the exact compatibility conflict.
	mWrite("/etc/openvpn/server1/config.ovpn", "ncp-disable\n", 0600)
	upstream, e := mRun("/usr/libexec/localmod/merlin/bin/openvpn", "--cd", "/etc/openvpn/server1", "--config", "config.ovpn", "--show-ciphers")
	if e == nil || !strings.Contains(upstream, "ncp-disable") {
		panic("expected removed upstream option: " + upstream)
	}
	original := mOK("/usr/libexec/localmod/merlin/vendor/openvpn", "--cd", "/etc/openvpn/server1", "--config", "config.ovpn", "--show-ciphers")
	adapted := mOK("/usr/sbin/openvpn", "--cd", "/etc/openvpn/server1", "--config", "config.ovpn", "--show-ciphers")
	if !strings.HasSuffix(adapted, original) || !strings.Contains(adapted, "retained factory OpenVPN for configured legacy option ncp-disable") {
		panic("legacy profile routing mismatch: " + adapted)
	}
	fmt.Printf("OPENVPN_LEGACY_OPTION_REPRODUCED %q\n", strings.TrimSpace(upstream))
	mRecord("factory_legacy_ncp_disable_profile_keeps_original_program_output_while_modern_default_remains_27")
	nrMust(os.MkdirAll("/etc/openvpn", 0700))
	mOK("/usr/sbin/openvpn", "--mktun", "--dev", "tun11")
	defer mOK("/usr/sbin/openvpn", "--rmtun", "--dev", "tun11")
	mVPNPKI()
	mOK("/usr/libexec/localmod/merlin/vendor/openvpn", "--genkey", "--secret", "/tmp/merlin/factory-static.key")
	for target, source := range map[string]string{"ca": "vpn-ca.crt", "crt": "client.crt", "key": "client.key", "static": "factory-static.key"} {
		mWrite("/jffs/openvpn/vpn_crt_client1_"+target, string(nrRead("/tmp/merlin/"+source)), 0600)
	}
	output := mOK("/usr/bin/qemu-arm", "-L", "/", "-E", "LD_PRELOAD=/work/build/native_hw_fixture.so:/work/build/merlin-vpn-config-fixture.so", "/work/build/merlin-vpn-config-probe", "1")
	for _, name := range []string{"ovpnc-up", "ovpnc-down", "ovpnc-route-up", "ovpnc-route-pre-down"} {
		path := "/etc/openvpn/" + name
		if _, e := os.Lstat(path); os.IsNotExist(e) {
			nrMust(os.Symlink("/sbin/rc", path))
		}
	}
	cfg := nrRead("/etc/openvpn/client1/config.ovpn")
	if !strings.Contains(output, "OFFICIAL_LIBVPN_CLIENT_CONFIG_RETURNED") || !bytes.Contains(cfg, []byte("Automatically generated configuration")) {
		panic(output)
	}
	out, e := mRun("/usr/sbin/openvpn", "--log", "/tmp/merlin/factory-config-openvpn.log", "--cd", "/etc/openvpn/client1", "--config", "config.ovpn", "--show-ciphers")
	if e != nil {
		log, _ := os.ReadFile("/tmp/merlin/factory-config-openvpn.log")
		panic(fmt.Sprintf("factory generated config parse: %v\n%s\n%s\nCONFIG\n%s", e, out, log, cfg))
	}
	fmt.Printf("FACTORY_CONFIG_SHA256 %x\n", sha256.Sum256(cfg))
	mRecord("retained_factory_libvpn_generates_real_client_configuration_accepted_by_new_option_parser")

}

func main() {
	if len(os.Args) > 1 && os.Args[1] == "dhcp-client" {
		mDHCPClient()
		return
	}
	nrMust(os.MkdirAll("/tmp/merlin", 0755))
	nrMust(os.MkdirAll("/jffs/.ssh", 0700))
	// The login fixture intentionally writes only its synthetic admin account.
	// Supply the unprivileged account used by the real dnsmasq default too.
	f, e := os.OpenFile("/var/passwd", os.O_APPEND|os.O_WRONLY, 0600)
	nrMust(e)
	_, e = f.WriteString("nobody:x:65534:65534:owned-dns-fixture:/tmp:/bin/false\n")
	nrMust(e)
	nrMust(f.Close())
	f, e = os.OpenFile("/etc/group", os.O_APPEND|os.O_WRONLY|os.O_CREATE, 0600)
	nrMust(e)
	_, e = f.WriteString("nobody:x:65534:\n")
	nrMust(e)
	nrMust(f.Close())
	ctx, cancel := context.WithTimeout(context.Background(), 270*time.Second)
	defer cancel()
	u := onlineUUStart(ctx)
	defer u.close()
	selected := os.Getenv("LOCALMOD_MERLIN_PROBE")
	if selected == "" {
		mVersions()
		mDNSChecks(u)
		mDHCP(u)
		mDownloads(u)
		mSSH(u)
		mUPnP(u)
		mVPN(u)
		mFactoryConfig()
	} else {
		switch selected {
		case "ssh":
			mSSH(u)
		case "upnp", "upnp-factory", "upnp-raw":
			mUPnP(u)
		case "vpn":
			mVPN(u)
		case "factory-config":
			mFactoryConfig()
		case "dns":
			mDNSChecks(u)
		case "dhcp":
			mDHCP(u)
		default:
			panic("unknown owned service probe")
		}
	}
	coUUAlive(u.pid)
	if u.calls.Load() != 1 || u.downloads.Load() != 1 || strings.Count(string(nrRead("/tmp/owned-uu-launches")), "start") != 1 {
		panic("unexpected UU restart")
	}
	if selected == "" {
		mRecord("all_component_flows_keep_original_uu_download_start_once_and_owned_data")
	}
	result := map[string]any{"full_suite": selected == "", "checks": merlinChecks, "versions": merlinVersions, "uu_api_requests": u.calls.Load(), "uu_downloads": u.downloads.Load(), "real_uu_monitor_executed": false}
	b, e := json.Marshal(result)
	nrMust(e)
	fmt.Println("MERLIN_RESULT " + string(b))
}
