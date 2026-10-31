package main

import "os"

func main() {
	if len(os.Args) == 2 && os.Args[1] == "controller" {
		interruptController()
		return
	}
	if len(os.Args) == 2 && os.Args[1] == "interrupt-run" {
		interruptWorker()
		return
	}
	interruptLegacyMain()
}
