// Native guest fixture for verifying launcher argv/environment forwarding.
package main
import("encoding/json";"os")
func main(){json.NewEncoder(os.Stdout).Encode(map[string]any{"args":os.Args,"preload":os.Getenv("LD_PRELOAD")});os.Exit(19)}
