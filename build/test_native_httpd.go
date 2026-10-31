package main

import (
 "context"
 "crypto/ecdsa"
 "crypto/elliptic"
 "crypto/rand"
 "crypto/tls"
 "crypto/x509"
 "crypto/x509/pkix"
 "encoding/base64"
 "encoding/pem"
 "fmt"
 "io"
 "math/big"
 "net"
 "net/http"
 "net/url"
 "os"
 "os/exec"
 "strings"
 "time"
)
func must(err error) { if err!=nil { panic(err) } }
func main(){
 ctx,cancel:=context.WithTimeout(context.Background(),38*time.Second);defer cancel()
 key,e:=ecdsa.GenerateKey(elliptic.P256(),rand.Reader);must(e)
 cert:=&x509.Certificate{SerialNumber:big.NewInt(1),Subject:pkix.Name{CommonName:"router.test"},DNSNames:[]string{"router.test"},IPAddresses:[]net.IP{net.ParseIP("192.168.77.1")},NotBefore:time.Now().Add(-time.Hour),NotAfter:time.Now().Add(time.Hour),KeyUsage:x509.KeyUsageDigitalSignature|x509.KeyUsageCertSign,ExtKeyUsage:[]x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth},IsCA:true,BasicConstraintsValid:true}
 der,e:=x509.CreateCertificate(rand.Reader,cert,cert,&key.PublicKey,key);must(e);keyDer,e:=x509.MarshalECPrivateKey(key);must(e)
 certPEM:=pem.EncodeToMemory(&pem.Block{Type:"CERTIFICATE",Bytes:der});must(os.WriteFile("/etc/cert.pem",certPEM,0600));must(os.WriteFile("/etc/key.pem",pem.EncodeToMemory(&pem.Block{Type:"EC PRIVATE KEY",Bytes:keyDer}),0600))
 roots:=x509.NewCertPool();if !roots.AppendCertsFromPEM(certPEM){panic("fixture certificate")}
 passed:=[]string{}
 for _,secure:=range []bool{false,true}{
  tokenName:="asus_token";if secure{tokenName="asus_s_token"}
  mode,base,port:="http","http://192.168.77.1:34080","34080";if secure{mode,base,port="https","https://192.168.77.1:34443","34443"}
  args:=[]string{"-L","/work/build/casefs/official_rootfs","-E","LD_PRELOAD=/work/build/httpd_bridge.so:/work/build/native_hw_fixture.so","/usr/libexec/localmod/httpd","-p",port};if secure{args=append(args,"-s")}
  log,e:=os.Create("/work/build/native_"+mode+"_server.log");must(e)
  cmd:=exec.CommandContext(ctx,"/usr/bin/qemu-arm",args...);cmd.Dir="/www";cmd.Stdout=log;cmd.Stderr=log;must(cmd.Start())
  transport:=&http.Transport{TLSClientConfig:&tls.Config{RootCAs:roots,ServerName:"router.test",MinVersion:tls.VersionTLS12},DisableKeepAlives:true}
  client:=&http.Client{Transport:transport,Timeout:4*time.Second,CheckRedirect:func(r *http.Request,via []*http.Request)error{return http.ErrUseLastResponse}}
  request:=func(method,path,token,body string)(*http.Response,string){
   req,e:=http.NewRequest(method,base+path,strings.NewReader(body));must(e)
   req.Header.Set("User-Agent","Mozilla/5.0 native-local-verification");req.Header.Set("Referer",base+"/Main_Login.asp");req.Header.Set("Origin",base)
   if body!=""{req.Header.Set("Content-Type","application/x-www-form-urlencoded");if strings.HasPrefix(path,"/_api/"){req.Header.Set("Content-Type","application/json")}};if token!=""{req.AddCookie(&http.Cookie{Name:tokenName,Value:token})}
   res,e:=client.Do(req);must(e);data,e:=io.ReadAll(res.Body);res.Body.Close();must(e);return res,string(data)
  }
  ready:=false;for i:=0;i<40;i++{c,e:=net.DialTimeout("tcp","192.168.77.1:"+port,100*time.Millisecond);if e==nil{c.Close();ready=true;break};time.Sleep(100*time.Millisecond)}
  if !ready{b,_:=os.ReadFile("/work/build/native_"+mode+"_server.log");panic("native server not ready: "+string(b))}
  res,body:=request("GET","/Main_Login.asp","","");if res.StatusCode!=200 || !strings.Contains(body,"login_authorization"){panic(fmt.Sprintf("%s login page %d %s",mode,res.StatusCode,body))}
  if secure && (res.TLS==nil || len(res.TLS.VerifiedChains)==0){panic("TLS was not certificate verified")}
  passed=append(passed,mode+"_native_login_page_and_transport")
  login:=func(password string)(*http.Response,string){form:=url.Values{"login_authorization":{base64.StdEncoding.EncodeToString([]byte("admin:"+password))},"next_page":{"index.asp"}};return request("POST","/login.cgi","",form.Encode())}
  res,body=login("wrong-local-password");if len(res.Cookies())!=0{panic("wrong password received session")};passed=append(passed,mode+"_wrong_password_rejected")
  res,body=login("local-test-password");token:="";for _,cookie:=range res.Cookies(){if cookie.Name==tokenName{token=cookie.Value}}
  if token==""{panic(fmt.Sprintf("%s valid login failed status=%d body=%s",mode,res.StatusCode,body))};passed=append(passed,mode+"_native_password_check_and_session_issuance")
  res,body=request("GET","/Module_NativeProbe.asp",token,"");if res.StatusCode!=200 || !strings.Contains(body,"NATIVE_VENDOR_PROTECTED"){panic(fmt.Sprintf("native protected page %d %s",res.StatusCode,body))};passed=append(passed,mode+"_native_protected_page_with_issued_token")
  res,body=request("GET","/_api/localmod_native_",token,"");if res.StatusCode!=200 || !strings.Contains(body,"real-native-session"){panic(fmt.Sprintf("%s real API %d %s",mode,res.StatusCode,body))};passed=append(passed,mode+"_issued_token_reaches_real_software_center")
  id:=51001;if secure{id=51002};payload:=fmt.Sprintf(`{"id":%d,"method":"native_probe.sh","params":[],"fields":{"localmod_native_input":"body-roundtrip"}}`,id)
  res,body=request("POST","/_api/",token,payload);if res.StatusCode!=200 || !strings.Contains(body,fmt.Sprint(id)){panic(fmt.Sprintf("%s API POST callback %d %s",mode,res.StatusCode,body))}
  res,body=request("GET","/_api/localmod_native_",token,"");if !strings.Contains(body,"body-roundtrip-pass"){panic("native POST body or callback was changed")};passed=append(passed,mode+"_native_post_body_and_real_callback")
  for _,bad:=range []string{"","invalid-local-token"}{res,body=request("GET","/_api/localmod_native_",bad,"");if strings.Contains(body,"real-native-session") || res.StatusCode==200{panic(fmt.Sprintf("%s invalid API session accepted %d %s",mode,res.StatusCode,body))}}
  passed=append(passed,mode+"_missing_and_invalid_sessions_blocked")
  logoutRes,_:=request("GET","/Logout.asp",token,"")
  res,body=request("GET","/_api/localmod_native_",token,"");if strings.Contains(body,"real-native-session") || res.StatusCode==200{panic(fmt.Sprintf("logout failed to revoke token: logout=%d; api=%d %s",logoutRes.StatusCode,res.StatusCode,body))};passed=append(passed,mode+"_logout_revokes_session")
  cmd.Process.Signal(os.Interrupt);cmd.Process.Kill();cmd.Wait();log.Close();transport.CloseIdleConnections()
 }
 for _,name:=range passed{fmt.Println("PASS",name)}
 fmt.Println("PASS pinned vendor HTTPd, libpasswd, mssl/OpenSSL and token handlers executed; only NVRAM/board inputs are synthetic")
}
