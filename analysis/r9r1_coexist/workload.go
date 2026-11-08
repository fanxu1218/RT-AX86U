package main

import (
	"bufio"
	"bytes"
	"context"
	"crypto/sha256"
	"crypto/tls"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"net"
	"net/http"
	"os"
	"strconv"
	"strings"
	"syscall"
	"time"
)

// One TLS handshake, split inside ClientHello. Signals never replay HTTP.
type splitHello struct {
	net.Conn
	ready, release chan struct{}
	first          bool
}

func (s *splitHello) Write(b []byte) (int, error) {
	if s.first || len(b) <= 8 {
		return s.Conn.Write(b)
	}
	s.first = true
	n, e := s.Conn.Write(b[:8])
	if e != nil {
		return n, e
	}
	close(s.ready)
	<-s.release
	m, e := s.Conn.Write(b[8:])
	return n + m, e
}

func (c *coexistRun) handshakeProbe() {
	x := c.x
	rows := []map[string]any{}
	for i := 0; i < 14; i++ {
		raw, e := net.DialTimeout("tcp4", "192.168.77.1:34443", 3*time.Second)
		nrMust(e)
		nrMust(raw.SetDeadline(time.Now().Add(9 * time.Second)))
		split := &splitHello{Conn: raw, ready: make(chan struct{}), release: make(chan struct{})}
		cfg := x.s.client.Transport.(*http.Transport).TLSClientConfig.Clone()
		cfg.ServerName = "192.168.77.1"
		conn := tls.Client(split, cfg)
		done := make(chan error, 1)
		go func() { done <- conn.Handshake() }()
		select {
		case <-split.ready:
		case e = <-done:
			panic(fmt.Sprintf("ClientHello not sent: %v", e))
		}
		time.Sleep(180 * time.Millisecond)
		kind := "control"
		if i >= 4 && i < 8 {
			kind = "SIGALRM"
			nrMust(x.s.cmd.Process.Signal(syscall.SIGALRM))
		}
		if i >= 8 && i < 12 {
			kind = "SIGCHLD"
			nrMust(x.s.cmd.Process.Signal(syscall.SIGCHLD))
		}
		if i == 12 {
			kind = "timeout"
			time.Sleep(6500 * time.Millisecond)
		} else if i == 13 {
			kind = "repeated_signal_timeout"
			for j := 0; j < 12; j++ {
				nrMust(x.s.cmd.Process.Signal(syscall.SIGALRM))
				time.Sleep(500 * time.Millisecond)
			}
		} else {
			time.Sleep(180 * time.Millisecond)
		}
		close(split.release)
		e = <-done
		code := 0
		valid := false
		if e == nil {
			_, e = fmt.Fprintf(conn, "GET /_localmod/status HTTP/1.0\r\nHost: 192.168.77.1:34443\r\nUser-Agent: Mozilla/5.0 native-lifecycle-fixture\r\nCookie: asus_s_token=%s\r\n\r\n", x.s.token)
			if e == nil {
				var r *http.Response
				r, e = http.ReadResponse(bufio.NewReader(conn), nil)
				if e == nil {
					code = r.StatusCode
					var b []byte
					b, e = io.ReadAll(r.Body)
					r.Body.Close()
					valid = code == 200 && json.Valid(b)
				}
			}
		}
		conn.Close()
		raw.Close()
		row := map[string]any{"kind": kind, "code": code, "valid": valid, "error": fmt.Sprint(e)}
		rows = append(rows, row)
		fmt.Printf("COEXIST_HANDSHAKE_CASE %v\n", row)
		c.core()
	}
	for i := 0; i < 6; i++ {
		c.event("center")
		for j := 0; j < 12; j++ {
			c.core()
		}
	}
	c.data()
	b, _ := json.Marshal(map[string]any{"handshake_cases": rows, "center_restart_cycles": 6, "queries": x.queries, "data_preserved": true})
	fmt.Printf("COEXIST_PROBE_RESULT %s\n", b)
	for _, p := range []string{"/tmp/coexist-tls-errors.log", "/tmp/coexist-tls-write-errors.log", nrOutput("soak-https-restart-server.log")} {
		if b, e := os.ReadFile(p); e == nil {
			fmt.Printf("PROBE_DIAGNOSTIC %s\n%s\n", p, b)
		}
	}
}

type coexistRun struct {
	x       *soak
	procs   map[string]*mProcess
	args    map[string][]string
	files   map[string][]byte
	db      map[string]string
	samples []map[string]any
	checks  map[string]int
	upnp    *http.Client
}

func (c *coexistRun) start(name string, args ...string) {
	c.args[name] = args
	c.procs[name] = mStart(name, args...)
}
func (c *coexistRun) restart(name string) {
	c.procs[name].stop()
	c.procs[name] = mStart(name, c.args[name]...)
}
func (c *coexistRun) rpc(method, action string) string {
	c.x.id++
	b, _ := json.Marshal(map[string]any{"id": c.x.id, "method": method, "params": []string{action}, "fields": ""})
	code, body := c.x.s.request("POST", "/_api/", string(b))
	var r map[string]json.RawMessage
	if code != 200 || json.Unmarshal([]byte(body), &r) != nil || r["result"] == nil {
		panic(fmt.Sprintf("native RPC %s code%d body%s", method, code, body))
	}
	return body
}
func (c *coexistRun) proxy(port int) string {
	conn, e := net.DialTimeout("tcp4", "127.0.0.1:35016", time.Second)
	nrMust(e)
	defer conn.Close()
	nrMust(conn.SetDeadline(time.Now().Add(5 * time.Second)))
	_, e = conn.Write([]byte{5, 1, 0})
	nrMust(e)
	b := make([]byte, 2)
	_, e = io.ReadFull(conn, b)
	nrMust(e)
	if !bytes.Equal(b, []byte{5, 0}) {
		panic("SOCKS authentication method")
	}
	_, e = conn.Write([]byte{5, 1, 0, 1, 127, 0, 0, 1, byte(port >> 8), byte(port)})
	nrMust(e)
	b = make([]byte, 10)
	if _, e = io.ReadFull(conn, b); e != nil || b[1] != 0 {
		return ""
	}
	_, e = io.WriteString(conn, "GET /owned HTTP/1.0\r\nHost: localhost\r\n\r\n")
	nrMust(e)
	data, _ := io.ReadAll(conn)
	return string(data)
}
func (c *coexistRun) proxyOK() {
	if !strings.Contains(c.proxy(35017), "owned-coexist-route") {
		panic("Fancyss SOCKS/VLESS did not forward")
	}
	c.checks["proxy_queries"]++
}
func (c *coexistRun) data() {
	c.x.data()
	for p, b := range c.files {
		if !bytes.Equal(b, nrRead(p)) {
			panic("configuration/key changed " + p)
		}
	}
	for k, v := range c.db {
		if strings.TrimSpace(nrCommand("/usr/bin/dbus", "get", k)) != v {
			panic("Fancyss config key changed " + k)
		}
	}
}
func (c *coexistRun) core() {
	c.x.query([]string{"status", "version"}[c.x.queries%2])
	if mDNS("udp") != "198.51.100.42" || mDNS("tcp") != "198.51.100.42" {
		panic("DNS query failed")
	}
	c.checks["dns_queries"] += 2
	c.proxyOK()
}
func (c *coexistRun) sshReady() {
	mWait("dropbear", func() bool {
		conn, e := net.DialTimeout("tcp4", "127.0.0.1:35322", time.Second)
		if e != nil {
			return false
		}
		defer conn.Close()
		conn.SetDeadline(time.Now().Add(time.Second))
		b := make([]byte, 128)
		n, _ := conn.Read(b)
		return strings.HasPrefix(string(b[:n]), "SSH-2.0-dropbear")
	})
}
func (c *coexistRun) ssh() {
	out := mOK("/usr/bin/dbclient", "-T", "-o", "StrictHostKeyChecking=yes", "-i", "/tmp/merlin/ssh-client.key", "-p", "35322", "admin@127.0.0.1", "printf COEXIST_SSH; test -z \"$LD_LIBRARY_PATH$LD_PRELOAD\"")
	if !strings.Contains(out, "COEXIST_SSH") {
		panic("SSH output")
	}
	c.checks["ssh_queries"]++
}
func (c *coexistRun) vpn() {
	mOK("/bin/ping", "-c", "1", "-W", "3", "-I", "ovpnc0", "10.244.0.1")
	c.checks["tun_traffic"]++
}
func (c *coexistRun) readyVPN() {
	mWait("openvpn-client", func() bool {
		_, e := mRun("/bin/ping", "-c", "1", "-W", "1", "-I", "ovpnc0", "10.244.0.1")
		return e == nil
	})
}
func (c *coexistRun) mapping() {
	fields := "<NewRemoteHost></NewRemoteHost><NewExternalPort>45001</NewExternalPort><NewProtocol>TCP</NewProtocol><NewInternalPort>45001</NewInternalPort><NewInternalClient>192.168.77.1</NewInternalClient><NewEnabled>1</NewEnabled><NewPortMappingDescription>owned-test</NewPortMappingDescription><NewLeaseDuration>120</NewLeaseDuration>"
	code, b := mSOAP(c.upnp, "AddPortMapping", fields)
	if code != 200 {
		panic(fmt.Sprintf("UPnP add %d %s", code, b))
	}
	if !strings.Contains(mOK("/usr/sbin/iptables", "-t", "nat", "-S", "LOCALMOD_UPNP"), "45001") {
		panic("UPnP postrouting rule absent")
	}
	key := "<NewRemoteHost></NewRemoteHost><NewExternalPort>45001</NewExternalPort><NewProtocol>TCP</NewProtocol>"
	code, b = mSOAP(c.upnp, "GetSpecificPortMappingEntry", key)
	if code != 200 || !strings.Contains(b, "192.168.77.1") {
		panic("UPnP query")
	}
	code, b = mSOAP(c.upnp, "DeletePortMapping", key)
	if code != 200 {
		panic("UPnP delete " + b)
	}
	if strings.Contains(mOK("/usr/sbin/iptables", "-t", "nat", "-S", "VUPNP"), "45001") {
		panic("UPnP DNAT remains after delete")
	}
	c.checks["upnp_cycles"]++
}
func (c *coexistRun) downloads() {
	url := "https://repo.fixture.test:35001/onlineprobe/v1.tar.gz"
	expected := c.x.repo.blobs["/onlineprobe/v1.tar.gz"]
	mOK("/usr/sbin/curl", "--noproxy", "*", "--fail", "--max-time", "10", "--cacert", "/tmp/online-repo-ca.pem", "-o", "/tmp/merlin/curl.bin", url)
	mOK("/usr/sbin/wget", "-q", "-O", "/tmp/merlin/wget.bin", url)
	for _, p := range []string{"/tmp/merlin/curl.bin", "/tmp/merlin/wget.bin"} {
		if !bytes.Equal(expected, nrRead(p)) {
			panic("download bytes differ")
		}
	}
	c.checks["curl_wget_https_pairs"]++
}
func (c *coexistRun) sample() {
	ids := map[string]int{"httpd": c.x.s.cmd.Process.Pid, "httpdb": pid("httpdb"), "skipd": pid("skipd"), "ddnsgo": pid("ddnsgo"), "uu": c.x.u.pid}
	for name, p := range c.procs {
		ids[name] = p.cmd.Process.Pid
	}
	row := map[string]any{"elapsed_seconds": time.Since(c.x.started).Seconds(), "queries": c.x.queries, "events": c.x.events}
	for name, p := range ids {
		exe, e := os.Readlink(fmt.Sprintf("/proc/%d/exe", p))
		nrMust(e)
		r, f := rss(p), fds(p)
		if r <= 0 || f < 0 {
			panic("dead sampled process " + name)
		}
		row[name] = map[string]any{"pid": p, "rss_kib": r, "fds": f, "executable": exe}
	}
	c.samples = append(c.samples, row)
	b, _ := json.Marshal(row)
	fmt.Printf("COEXIST_SAMPLE %s\n", b)
}
func (c *coexistRun) event(kind string) {
	for _, k := range []string{"abort", "partial", "backend", "center", "ddns", "uu", "tls", "signals"} {
		if kind == k {
			c.x.event(kind)
			c.data()
			c.core()
			return
		}
	}
	began := time.Now()
	c.data()
	fmt.Println("COEXIST_EVENT_BEGIN", kind)
	finishWindow := c.x.window(kind+"_restart", false)
	switch kind {
	case "dns":
		c.restart("dnsmasq")
		mWait("dnsmasq", func() bool { return mDNS("udp") == "198.51.100.42" })
	case "ssh":
		c.restart("dropbear")
		mWait("dropbear", func() bool {
			_, e := mRun("/usr/bin/dbclient", "-T", "-o", "StrictHostKeyChecking=yes", "-i", "/tmp/merlin/ssh-client.key", "-p", "35322", "admin@127.0.0.1", "true")
			return e == nil
		})
	case "upnp":
		c.restart("miniupnpd")
		c.upnpReady()
		c.mapping()
	case "vpn-client":
		c.restart("openvpn-client")
		c.readyVPN()
	case "fancy-client":
		c.restart("xray-client")
		c.xrayReady(35016)
		c.proxyOK()
	case "nat":
		mOK("/usr/sbin/iptables-restore", "/tmp/merlin/nat.restore")
		c.mapping()
		p := mOK("/usr/sbin/iptables", "-t", "nat", "-S", "POSTROUTING")
		if strings.Count(p, "-j LOCALMOD_UPNP") != 1 {
			panic("UPnP NAT hook duplicated/lost")
		}
	case "proxy-upstream":
		c.procs["xray-server"].stop()
		if strings.Contains(c.proxy(35017), "owned-coexist-route") {
			panic("proxy bypassed dead upstream")
		}
		c.procs["xray-server"] = mStart("xray-server", c.args["xray-server"]...)
		c.xrayReady(35015)
		c.proxyOK()
	case "vpn-upstream":
		c.procs["openvpn-server"].stop()
		if _, e := mRun("/bin/ping", "-c", "1", "-W", "1", "-I", "ovpnc0", "10.244.0.1"); e == nil {
			panic("TUN ping bypassed stopped VPN server")
		}
		time.Sleep(7 * time.Second)
		c.procs["openvpn-server"] = mStart("openvpn-server", c.args["openvpn-server"]...)
		c.readyVPN()
	default:
		panic("unknown coexist event " + kind)
	}
	fmt.Println("COEXIST_WINDOW", finishWindow())
	c.x.events++
	c.x.counts[kind]++
	c.core()
	c.data()
	fmt.Printf("COEXIST_EVENT kind=%s seconds=%.3f\n", kind, time.Since(began).Seconds())
}
func (c *coexistRun) xrayReady(port int) {
	mWait("xray-client", func() bool {
		p, e := net.DialTimeout("tcp4", fmt.Sprintf("127.0.0.1:%d", port), time.Second)
		if e == nil {
			p.Close()
		}
		return e == nil
	})
}
func (c *coexistRun) upnpReady() {
	mWait("miniupnpd", func() bool {
		r, e := c.upnp.Get("http://192.168.77.1:35323/rootDesc.xml")
		if e != nil {
			return false
		}
		defer r.Body.Close()
		return r.StatusCode == 200
	})
}
func (c *coexistRun) setupComponents() {
	mWrite("/tmp/merlin/dns.hosts", "198.51.100.42 owned.test\n", 0644)
	mWrite("/tmp/merlin/dnsmasq.conf", "port=35353\nlisten-address=127.0.0.1\nbind-interfaces\nno-resolv\nno-hosts\naddn-hosts=/tmp/merlin/dns.hosts\npid-file=/tmp/merlin/dnsmasq.pid\nlog-facility=-\n", 0600)
	c.start("dnsmasq", "/usr/sbin/dnsmasq", "--keep-in-foreground", "--conf-file=/tmp/merlin/dnsmasq.conf")
	mWait("dnsmasq", func() bool { return mDNS("udp") == "198.51.100.42" })
	nrMust(os.Setenv("HOME", "/tmp"))
	mOK("/usr/bin/dropbearkey", "-t", "ed25519", "-f", "/tmp/merlin/ssh-client.key")
	mOK("/usr/libexec/localmod/merlin/vendor/dropbearkey", "-t", "ed25519", "-f", "/jffs/.ssh/dropbear_ed25519_host_key")
	mWrite("/tmp/.ssh/authorized_keys", mPublic("/tmp/merlin/ssh-client.key")+"\n", 0600)
	mWrite("/tmp/.ssh/known_hosts", "127.0.0.1 "+mPublic("/jffs/.ssh/dropbear_ed25519_host_key")+"\n", 0600)
	c.start("dropbear", "/usr/bin/qemu-arm", "-0", "dropbear", "-L", "/", "-E", "LD_PRELOAD=/work/build/native_hw_fixture.so", "/usr/sbin/dropbear", "-F", "-E", "-s", "-p", "127.0.0.1:35322", "-r", "/jffs/.ssh/dropbear_ed25519_host_key")
	c.sshReady()
	c.ssh()
	for _, a := range [][]string{{"-t", "nat", "-N", "VUPNP"}, {"-t", "nat", "-N", "VSERVER"}, {"-N", "FUPNP"}} {
		mOK(append([]string{"/usr/sbin/iptables"}, a...)...)
	}
	mWrite("/tmp/merlin/upnp.conf", "ext_ifname=wan0\nlistening_ip=192.168.77.1/24\nport=35323\nenable_upnp=yes\nenable_natpmp=yes\nsecure_mode=yes\nupnp_forward_chain=FUPNP\nupnp_nat_chain=VUPNP\nnotify_interval=60\nsystem_uptime=yes\nfriendly_name=owned-coexist\nmodel_name=RT-AX86U\nmodel_number=RT-AX86U\nserial=owned\nuuid=3ddcd1d3-2380-45f5-b069-020000000001\nlease_file=/jffs/upnp-owned.leases\nallow 45000-45010 192.168.77.0/24 45000-45010\ndeny 0-65535 0.0.0.0/0 0-65535\n", 0600)
	c.upnp = &http.Client{Transport: &http.Transport{DialContext: (&net.Dialer{Timeout: time.Second, LocalAddr: &net.TCPAddr{IP: net.ParseIP("192.168.77.1")}}).DialContext, DisableKeepAlives: true}, Timeout: 5 * time.Second}
	c.start("miniupnpd", "/usr/sbin/miniupnpd", "-d", "-f", "/tmp/merlin/upnp.conf", "-P", "/tmp/merlin/miniupnpd.pid")
	c.upnpReady()
	c.mapping()
	mWrite("/tmp/merlin/nat.restore", "*nat\n:PREROUTING ACCEPT [0:0]\n:POSTROUTING ACCEPT [0:0]\n:OUTPUT ACCEPT [0:0]\n:VSERVER - [0:0]\n:VUPNP - [0:0]\n-A VSERVER -j VUPNP\nCOMMIT\n", 0600)
	mOK(mIP("netns", "add", "merlin-vpn-server")...)
	mOK(mIP("link", "add", "vpnctl0", "type", "veth", "peer", "name", "vpnctl1")...)
	mOK(mIP("link", "set", "vpnctl1", "netns", "merlin-vpn-server")...)
	mOK(mIP("addr", "add", "192.0.2.1/30", "dev", "vpnctl0")...)
	mOK(mIP("link", "set", "vpnctl0", "up")...)
	mOK(mNS("merlin-vpn-server", "addr", "add", "192.0.2.2/30", "dev", "vpnctl1")...)
	mOK(mNS("merlin-vpn-server", "link", "set", "vpnctl1", "up")...)
	mOK(mNS("merlin-vpn-server", "link", "set", "lo", "up")...)
	mVPNPKI()
	common := "proto udp\nca /tmp/merlin/vpn-ca.crt\nverb 3\nauth SHA256\ndata-ciphers AES-256-GCM\npersist-key\npersist-tun\nping 2\nping-restart 6\n"
	mWrite("/tmp/merlin/server.ovpn", common+"dev ovpns0\ndev-type tun\nlocal 192.0.2.2\nport 35325\nserver 10.244.0.0 255.255.255.0\ntopology subnet\ncert /tmp/merlin/server.crt\nkey /tmp/merlin/server.key\ndh none\n", 0600)
	mWrite("/tmp/merlin/client.ovpn", common+"client\ndev ovpnc0\ndev-type tun\nremote 192.0.2.2 35325\nnobind\nroute-noexec\nremote-cert-tls server\nverify-x509-name server name\ncert /tmp/merlin/client.crt\nkey /tmp/merlin/client.key\n", 0600)
	c.start("openvpn-server", mIP("netns", "exec", "merlin-vpn-server", "/usr/sbin/openvpn", "--config", "/tmp/merlin/server.ovpn")...)
	c.start("openvpn-client", "/usr/sbin/openvpn", "--config", "/tmp/merlin/client.ovpn")
	c.readyVPN()
	for _, p := range []string{"/tmp/merlin/dnsmasq.conf", "/tmp/merlin/upnp.conf", "/tmp/merlin/server.ovpn", "/tmp/merlin/client.ovpn", "/tmp/merlin/client.key", "/tmp/merlin/server.key", "/tmp/merlin/vpn-ca.crt", "/jffs/.ssh/dropbear_ed25519_host_key"} {
		c.files[p] = nrRead(p)
	}
}
func (c *coexistRun) setupXray() {
	l, e := net.Listen("tcp4", "127.0.0.1:35017")
	nrMust(e)
	h := &http.Server{Handler: http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { fmt.Fprint(w, "owned-coexist-route") })}
	go h.Serve(l)
	id := "55f681c1-90d8-4a3e-97a1-0488498fe021"
	freedom := map[string]any{"protocol": "freedom", "settings": map[string]any{"finalRules": []any{map[string]any{"action": "allow", "network": "tcp", "ip": []string{"127.0.0.1/32"}, "port": "35017"}}}}
	configs := []any{
		map[string]any{"log": map[string]string{"loglevel": "warning"}, "inbounds": []any{map[string]any{"listen": "127.0.0.1", "port": 35015, "protocol": "vless", "settings": map[string]any{"clients": []any{map[string]string{"id": id}}, "decryption": "none"}}}, "outbounds": []any{freedom}},
		map[string]any{"log": map[string]string{"loglevel": "warning"}, "inbounds": []any{map[string]any{"listen": "127.0.0.1", "port": 35016, "protocol": "socks", "settings": map[string]any{"auth": "noauth", "udp": false}}}, "outbounds": []any{map[string]any{"protocol": "vless", "settings": map[string]any{"vnext": []any{map[string]any{"address": "127.0.0.1", "port": 35015, "users": []any{map[string]string{"id": id, "encryption": "none"}}}}}}}},
	}
	for i, cfg := range configs {
		p := fmt.Sprintf("/koolshare/configs/fancyss/coexist-%d.json", i)
		b, _ := json.Marshal(cfg)
		mWrite(p, string(b), 0600)
		name := []string{"xray-server", "xray-client"}[i]
		c.start(name, "/koolshare/bin/xray", "run", "-c", p)
		c.xrayReady(35015 + i)
		c.files[p] = b
	}
	c.proxyOK()
}
func main() {
	if len(os.Args) > 1 && os.Args[1] == "dhcp-client" {
		mDHCPClient()
		return
	}
	seconds, e := strconv.Atoi(os.Getenv("COEXIST_SECONDS"))
	nrMust(e)
	if seconds != 600 && seconds != 3600 {
		panic("invalid run duration")
	}
	ctx, cancel := context.WithTimeout(context.Background(), time.Duration(seconds)*time.Second+15*time.Minute)
	defer cancel()
	x := &soak{ctx: ctx, id: 91000, counts: map[string]int{}, sentinels: map[string][]byte{}}
	c := &coexistRun{x: x, procs: map[string]*mProcess{}, args: map[string][]string{}, files: map[string][]byte{}, db: map[string]string{}, checks: map[string]int{}}
	defer func() {
		if p := recover(); p != nil {
			fmt.Println("COEXIST_FAILURE", p)
			for _, p := range []string{"/tmp/upload/soft_log.txt", "/tmp/.localmod/bootstrap.log", nrOutput("coexist-server.log"), nrOutput("soak-https-restart-server.log"), "/tmp/coexist-tls-errors.log", "/tmp/coexist-tls-write-errors.log", "/tmp/https-relay-trace"} {
				if b, e := os.ReadFile(p); e == nil {
					if len(b) > 16000 {
						b = b[len(b)-16000:]
					}
					fmt.Printf("DIAGNOSTIC %s\n%s\n", p, b)
				}
			}
			for name, p := range c.procs {
				if b, e := os.ReadFile("/tmp/merlin/" + name + ".log"); e == nil {
					if len(b) > 4000 {
						b = b[len(b)-4000:]
					}
					fmt.Printf("SERVICE_LOG %s\n%s\n", name, b)
				}
				p.stop()
			}
			panic(p)
		}
	}()
	nrMust(os.MkdirAll("/tmp/merlin", 0755))
	nrMust(os.MkdirAll("/jffs/.ssh", 0700))
	f, e := os.OpenFile("/var/passwd", os.O_APPEND|os.O_WRONLY, 0600)
	nrMust(e)
	_, e = f.WriteString("nobody:x:65534:65534:owned-dns:/tmp:/bin/false\n")
	nrMust(e)
	f.Close()
	mWrite("/tmp/https-trace-quiet", "1", 0600)
	fmt.Println("COEXIST_SETUP native_https_and_uu")
	x.repo = onlineRepository()
	defer x.repo.close()
	x.s = nrStart(ctx, "coexist", true)
	defer func() { x.s.stop() }()
	x.s.login()
	x.u = onlineUUStart(ctx)
	x.launches = 1
	defer func() { x.u.close() }()
	for _, p := range []string{"/jffs/uu-cache/uu.tar.gz", "/jffs/uu-cache/uu.tar.gz.md5", "/jffs/uu-state/user.dat", "/tmp/uu.tar.gz"} {
		mWrite(p, "coexist-owned-sentinel:"+p, 0600)
		x.sentinels[p] = nrRead(p)
	}
	var real struct {
		Packages []struct {
			Module, Phase, Path string
			Version             string `json:"catalog_version"`
			MD5                 string `json:"md5"`
		}
	}
	nrMust(json.Unmarshal(nrRead("/work/build/real_plugin_inputs.json"), &real))
	for _, p := range real.Packages {
		if p.Module == "ddnsgo" && p.Phase == "current" {
			x.repo.apps["ddnsgo-current"] = onlineApp{p.Module, p.Module, p.Version, p.MD5, "ddnsgo/current.tar.gz"}
			x.repo.blobs["/ddnsgo/current.tar.gz"] = nrRead("/work/" + p.Path)
		}
	}
	t := &onlineTest{s: x.s, repo: x.repo, uu: x.u, id: x.id, sentinels: x.sentinels, archive: nrRead("/jffs/cert.tgz")}
	fmt.Println("COEXIST_SETUP real_ddnsgo_install")
	t.operation("ddnsgo-current", "", true)
	x.id = t.id
	x.startDDNS(false)
	var fancy struct {
		Packages []struct {
			Phase, Version string
			AdaptedPath    string `json:"adapted_path"`
			SHA            string `json:"adapted_sha256"`
			Files          map[string]struct {
				SHA string `json:"sha256"`
			}
		}
	}
	nrMust(json.Unmarshal(nrRead("/work/build/fancyss_inputs.json"), &fancy))
	nrMust(os.Remove("/bin/uname"))
	mWrite("/bin/uname", "#!/bin/sh\ncase \"$*\" in -r) echo 4.1.52;; -m) echo aarch64;; *) exec /bin/busybox uname \"$@\";; esac\n", 0755)
	fmt.Println("COEXIST_SETUP real_fancyss_install")
	for _, p := range fancy.Packages {
		if p.Phase != "current" {
			continue
		}
		blob := nrRead("/work/" + p.AdaptedPath)
		if fmt.Sprintf("%x", sha256.Sum256(blob)) != p.SHA {
			panic("Fancyss archive SHA")
		}
		mWrite("/tmp/upload/coexist-fancyss.tar.gz", string(blob), 0600)
		t.id = x.id
		t.rpc("ks_tar_install.sh", "", map[string]string{"soft_name": "coexist-fancyss.tar.gz"})
		x.id = t.id
		end := time.Now().Add(300 * time.Second)
		done := false
		for time.Now().Before(end) {
			b, _ := os.ReadFile("/tmp/upload/soft_log.txt")
			_, lock := os.Stat("/tmp/.localmod/plugin-operation.lock")
			if strings.Contains(string(b), "XU6J03M6") && os.IsNotExist(lock) {
				done = true
				break
			}
			time.Sleep(200 * time.Millisecond)
		}
		if !done || strings.TrimSpace(nrCommand("/usr/bin/dbus", "get", "softcenter_installing_result")) != "0" {
			panic("Fancyss install failed")
		}
		if fmt.Sprintf("%x", sha256.Sum256(nrRead("/koolshare/bin/xray"))) != p.Files["bin/xray"].SHA {
			panic("Xray package identity")
		}
	}
	mWrite("/koolshare/configs/fancyss/coexist-retained.conf", "owned synthetic configuration\n", 0600)
	c.files["/koolshare/configs/fancyss/coexist-retained.conf"] = nrRead("/koolshare/configs/fancyss/coexist-retained.conf")
	node, _ := json.Marshal(map[string]string{"type": "0", "name": "owned-soak-node", "group": "manual", "server": "retained.invalid", "port": "443", "mode": "1", "method": "aes-128-gcm", "password": "owned-test-secret-not-real-account", "_source": "manual"})
	for k, v := range map[string]string{"fss_data_secret_mode": "raw", "fss_node_next_id": "2", "ss_basic_enable": "0", "ss_basic_interval": "4", "fss_data_schema": "2", "fss_node_current": "1", "fss_node_order": "1", "fss_node_1": base64.StdEncoding.EncodeToString(node)} {
		mOK("/usr/bin/dbus", "set", k+"="+v)
		c.db[k] = v
	}
	x.version = strings.TrimSpace(nrCommand("/koolshare/bin/ddnsgo", "-v"))
	x.db = nrCommand("/usr/bin/dbus", "list", "ddnsgo_")
	x.config = nrRead("/koolshare/configs/ddnsgo/default.yaml")
	x.cert = nrRead("/jffs/cert.tgz")
	fmt.Println("COEXIST_SETUP six_components")
	c.setupComponents()
	c.setupXray()
	defer func() {
		for _, p := range c.procs {
			p.stop()
		}
	}()
	mDHCP(x.u)
	c.data()
	c.downloads()
	c.rpc("ss_status.sh", "1")
	if os.Getenv("COEXIST_PROBE") == "1" {
		c.handshakeProbe()
		return
	}
	x.started = time.Now()
	kinds := []string{"abort", "partial", "backend", "center", "ddns", "uu", "tls", "signals", "dns", "ssh", "upnp", "vpn-client", "fancy-client", "nat", "proxy-upstream", "vpn-upstream"}
	period := 100 * time.Second
	if seconds == 600 {
		period = 10 * time.Second
	}
	nextEvent := x.started.Add(period)
	nextSample := x.started
	nextDeep := x.started
	deadline := x.started.Add(time.Duration(seconds) * time.Second)
	c.sample()
	for time.Now().Before(deadline) {
		tick := time.Now()
		if !tick.Before(nextEvent) {
			c.event(kinds[x.events%len(kinds)])
			nextEvent = nextEvent.Add(period)
		}
		c.core()
		if time.Now().After(nextDeep) {
			c.ssh()
			c.vpn()
			c.mapping()
			c.downloads()
			c.rpc("ss_status.sh", "1")
			code, page := x.s.request("GET", "/Module_Softcenter.asp", "")
			inline := func(text string) string {
				marker := `<script type="module">`
				i := strings.Index(text, marker)
				if i < 0 {
					panic("inline frontend absent")
				}
				text = text[i+len(marker):]
				j := strings.Index(text, "</script>")
				if j < 0 {
					panic("inline frontend incomplete")
				}
				return text[:j]
			}
			if code != 200 || !strings.Contains(page, "v2 release assets") || inline(page) != inline(string(nrRead("/rom/etc/koolshare/webs/Module_Softcenter.asp"))) {
				panic("software center frontend unavailable")
			}
			c.checks["core_page_queries"]++
			nextDeep = time.Now().Add(30 * time.Second)
		}
		if time.Now().After(nextSample) {
			c.data()
			c.sample()
			nextSample = time.Now().Add(25 * time.Second)
		}
		if delay := time.Until(tick.Add(2 * time.Second)); delay > 0 {
			time.Sleep(delay)
		}
	}
	c.core()
	c.data()
	c.sample()
	r := map[string]any{"duration_seconds": time.Since(x.started).Seconds(), "requested_seconds": seconds, "started_utc": x.started.UTC().Format(time.RFC3339), "finished_utc": time.Now().UTC().Format(time.RFC3339), "queries": x.queries, "events": x.events, "event_kinds": kinds, "counts": x.counts, "service_checks": c.checks, "samples": c.samples, "data_preserved": true, "unplanned_failures": 0, "uu_launches": x.launches, "actual_fancyss_global_proxy_enabled": false}
	for _, kind := range kinds {
		minimum := 1
		if seconds == 3600 {
			minimum = 2
		}
		if x.counts[kind] < minimum {
			panic("incomplete event coverage " + kind)
		}
	}
	b, _ := json.Marshal(r)
	fmt.Printf("COEXIST_RESULT %s\n", b)
	fmt.Println("PASS coexist continuous queries restarts faults and preserved data")
}
