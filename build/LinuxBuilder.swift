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
      ((CommandLine.arguments.count == 5 || CommandLine.arguments.count == 6) && CommandLine.arguments[4] == "--readonly") else {
    fputs("usage: LinuxBuilder kernel initramfs workspace [--readonly [owned-state.img]]\n", stderr)
    exit(2)
}
let readOnly = CommandLine.arguments.count >= 5
let stateDisk = CommandLine.arguments.count == 6
let config = VZVirtualMachineConfiguration()
let loader = VZLinuxBootLoader(kernelURL: URL(fileURLWithPath: CommandLine.arguments[1]))
loader.initialRamdiskURL = URL(fileURLWithPath: CommandLine.arguments[2])
loader.commandLine = "console=hvc0 quiet panic=-1" + (readOnly ? " localmod_readonly=1" : "") + (stateDisk ? " localmod_state_disk=1" : "")
config.bootLoader = loader
let fixtureCPUs = ProcessInfo.processInfo.environment["LOCALMOD_TEST_CPUS"].flatMap(Int.init) ?? 2
guard (1...2).contains(fixtureCPUs) else { fputs("Invalid fixture CPU count\n", stderr); exit(2) }
config.cpuCount = fixtureCPUs
config.memorySize = 1024 * 1024 * 1024
let console = VZVirtioConsoleDeviceSerialPortConfiguration()
console.attachment = VZFileHandleSerialPortAttachment(fileHandleForReading: nil,
                                                     fileHandleForWriting: .standardOutput)
config.serialPorts = [console]
config.entropyDevices = [VZVirtioEntropyDeviceConfiguration()]
config.networkDevices = []
config.storageDevices = []
if stateDisk {
    let disk = URL(fileURLWithPath: CommandLine.arguments[5]).resolvingSymlinksInPath()
    let owned = URL(fileURLWithPath: CommandLine.arguments[3]).resolvingSymlinksInPath().appendingPathComponent("build/interrupt-private").path + "/"
    guard disk.path.hasPrefix(owned), disk.pathExtension == "img",
          (try? FileManager.default.attributesOfItem(atPath: disk.path)[.size] as? NSNumber)?.intValue == 96 * 1024 * 1024 else {
        fputs("Only an owned 96 MiB interruption fixture disk is permitted\n", stderr); exit(2)
    }
    do {
        let attachment = try VZDiskImageStorageDeviceAttachment(url: disk, readOnly: false,
                                                              cachingMode: .uncached, synchronizationMode: .full)
        config.storageDevices = [VZVirtioBlockDeviceConfiguration(attachment: attachment)]
    } catch { fputs("Fixture disk: \(error)\n", stderr); exit(1) }
}
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
