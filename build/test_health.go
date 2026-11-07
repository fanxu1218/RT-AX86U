package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"os"
	"strings"
	"time"
)

func main() {
	ctx, cancel := context.WithTimeout(context.Background(), 120*time.Second)
	defer cancel()
	s := nrStart(ctx, "health", true)
	defer s.stop()
	checks := map[string]bool{}
	must := func(ok bool, name string) {
		if !ok {
			panic(name)
		}
		checks[name] = true
	}
	for _, p := range []string{"/_localmod/status", "/_localmod/diagnostics"} {
		code, _ := s.request("GET", p, "")
		must(code == 401, "no_cookie_denied"+p)
	}
	s.token = "invalid-owned-token"
	code, _ := s.request("GET", "/_localmod/status", "")
	must(code == 401, "invalid_cookie_denied")
	s.token = ""
	s.login()
	coBackendReady()
	u := onlineUUStart(ctx)
	defer u.close()
	cert := nrRead("/jffs/cert.tgz")
	secret := "never-export-owned-secret-accounts-and-token"
	nrCommand("/usr/bin/dbus", "set", "health_secret="+secret)
	nrMust(os.MkdirAll("/jffs/uu-state", 0700))
	nrMust(os.WriteFile("/jffs/uu-state/account", []byte(secret), 0600))
	nrMust(os.WriteFile("/tmp/.localmod/events.log", []byte(secret), 0600))
	nrCommand("/usr/libexec/localmod/localmod-status", "record", "ddnsgo", "finished", "0")
	query := func(expected string) {
		code, body := s.request("GET", "/_localmod/diagnostics", "")
		var x struct {
			Schema     int
			Checkpoint string
			Last       map[string]any `json:"last_operation"`
		}
		nrMust(json.Unmarshal([]byte(body), &x))
		must(code == 200 && x.Schema == 1 && x.Checkpoint == expected, "status_"+expected)
		must(!strings.Contains(body, secret) && !strings.Contains(body, s.token) && !strings.Contains(body, "BEGIN CERTIFICATE"), "redacted_"+expected)
	}
	query("none")
	code, operationBody := s.request("GET", "/_localmod/status", "")
	must(code == 200 && strings.Contains(operationBody, `"module":"ddnsgo","state":"finished","code":0`), "recent_operation_record_available")
	code, _ = s.request("POST", "/_localmod/status", "{}")
	must(code == 405, "health_endpoint_is_readonly")
	code, body := s.request("GET", "/Module_Localmod.asp", "")
	must(code == 200 && strings.Contains(body, "/_localmod/status") && !strings.Contains(body, "@REVISION@"), "authenticated_page_served")
	nrCommand("/bin/sh", "/usr/libexec/localmod/bootstrap.sh", "stop")
	nrMust(os.MkdirAll("/jffs/.localmod/plugin-txn/active", 0700))
	query("pending")
	code, _ = s.request("POST", "/_api/", `{"id":1,"method":"test"}`)
	must(code == 423, "write_gate_closed_during_checkpoint")
	nrMust(os.RemoveAll("/jffs/.localmod/plugin-txn"))
	nrMust(os.WriteFile("/jffs/.localmod/plugin-txn", []byte("owned-invalid-store"), 0600))
	query("store-invalid")
	nrMust(os.Remove("/tmp/.localmod/last-operation"))
	nrMust(os.Symlink("/jffs/uu-state/account", "/tmp/.localmod/last-operation"))
	query("store-invalid")
	must(bytes.Equal(cert, nrRead("/jffs/cert.tgz")) && string(nrRead("/jffs/uu-state/account")) == secret, "certificate_and_uu_data_retained")
	coUUAlive(u.pid)
	nrMust(os.Remove("/tmp/.localmod/last-operation"))
	nrMust(os.Remove("/jffs/.localmod/plugin-txn"))
	old := s.token
	s.request("GET", "/Logout.asp", "")
	s.token = old
	code, _ = s.request("GET", "/_localmod/diagnostics", "")
	must(code == 401, "logout_revokes_diagnostics")
	s.token = ""
	s.login()
	query("none")
	b, e := json.Marshal(map[string]any{"checks": checks, "backend_stopped_readonly_available": true, "uu_owned_worker_alive": true})
	nrMust(e)
	fmt.Printf("HEALTH_RESULT %s\n", b)
}
