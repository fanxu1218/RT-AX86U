import Foundation
import Virtualization

final class Delegate: NSObject, VZVirtualMachineDelegate {
    func virtualMachineDidStop(_ virtualMachine: VZVirtualMachine) { exit(0) }
    func virtualMachine(_ virtualMachine: VZVirtualMachine, didStopWithError error: Error) {
        fputs("Linux builder stopped: \(error)\n", stderr)
        exit(1)
    }
}

guard CommandLine.arguments.count == 4 ||
      (CommandLine.arguments.count == 5 && CommandLine.arguments[4] == "--readonly") else {
    fputs("usage: LinuxBuilder kernel initramfs workspace [--readonly]\n", stderr)
    exit(2)
}
let readOnly = CommandLine.arguments.count == 5
let config = VZVirtualMachineConfiguration()
let loader = VZLinuxBootLoader(kernelURL: URL(fileURLWithPath: CommandLine.arguments[1]))
loader.initialRamdiskURL = URL(fileURLWithPath: CommandLine.arguments[2])
loader.commandLine = "console=hvc0 quiet panic=-1" + (readOnly ? " localmod_readonly=1" : "")
config.bootLoader = loader
config.cpuCount = 2
config.memorySize = 1024 * 1024 * 1024
let console = VZVirtioConsoleDeviceSerialPortConfiguration()
console.attachment = VZFileHandleSerialPortAttachment(fileHandleForReading: nil,
                                                     fileHandleForWriting: .standardOutput)
config.serialPorts = [console]
config.entropyDevices = [VZVirtioEntropyDeviceConfiguration()]
config.networkDevices = []
config.storageDevices = []
let fs = VZVirtioFileSystemDeviceConfiguration(tag: "workspace")
fs.share = VZSingleDirectoryShare(directory: VZSharedDirectory(
    url: URL(fileURLWithPath: CommandLine.arguments[3]), readOnly: readOnly))
config.directorySharingDevices = [fs]
do { try config.validate() } catch {
    fputs("Linux builder configuration: \(error)\n", stderr)
    exit(1)
}
let vm = VZVirtualMachine(configuration: config)
let delegate = Delegate()
vm.delegate = delegate
vm.start { result in
    if case .failure(let error) = result {
        fputs("Linux builder start: \(error)\n", stderr)
        exit(1)
    }
}
dispatchMain()
