using System;
using System.ComponentModel;
using System.Runtime.InteropServices;
public static class AuroraWinUsb {
 [StructLayout(LayoutKind.Sequential)] public struct Device { public uint cbSize; public Guid ClassGuid; public uint DevInst; public UIntPtr Reserved; }
 [StructLayout(LayoutKind.Sequential, CharSet=CharSet.Unicode)] public struct Params {
  public uint cbSize, Flags, FlagsEx; public IntPtr hwndParent, InstallMsgHandler, InstallMsgHandlerContext, FileQueue; public UIntPtr ClassInstallReserved; public uint Reserved;
  [MarshalAs(UnmanagedType.ByValTStr, SizeConst=260)] public string DriverPath;
 }
 [StructLayout(LayoutKind.Sequential, CharSet=CharSet.Unicode)] public struct Driver {
  public uint cbSize, DriverType; public UIntPtr Reserved;
  [MarshalAs(UnmanagedType.ByValTStr, SizeConst=256)] public string Description;
  [MarshalAs(UnmanagedType.ByValTStr, SizeConst=256)] public string MfgName;
  [MarshalAs(UnmanagedType.ByValTStr, SizeConst=256)] public string ProviderName;
  public System.Runtime.InteropServices.ComTypes.FILETIME DriverDate; public ulong DriverVersion;
 }
 [DllImport("setupapi.dll",SetLastError=true)] static extern IntPtr SetupDiCreateDeviceInfoList(IntPtr guid,IntPtr parent);
 [DllImport("setupapi.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern bool SetupDiOpenDeviceInfo(IntPtr set,string id,IntPtr parent,uint flags,ref Device dev);
 [DllImport("setupapi.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern bool SetupDiGetDeviceInstallParams(IntPtr set,ref Device dev,ref Params p);
 [DllImport("setupapi.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern bool SetupDiSetDeviceInstallParams(IntPtr set,ref Device dev,ref Params p);
 [DllImport("setupapi.dll",SetLastError=true)] static extern bool SetupDiBuildDriverInfoList(IntPtr set,ref Device dev,uint type);
 [DllImport("setupapi.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern bool SetupDiEnumDriverInfo(IntPtr set,ref Device dev,uint type,uint index,ref Driver driver);
 [DllImport("setupapi.dll")] static extern bool SetupDiDestroyDeviceInfoList(IntPtr set);
 [DllImport("newdev.dll",SetLastError=true)] static extern bool DiInstallDevice(IntPtr parent,IntPtr set,ref Device dev,ref Driver driver,uint flags,out bool reboot);
 static void Check(bool ok,string operation) { if (!ok) throw new Win32Exception(Marshal.GetLastWin32Error(),operation); }
 public static string Run(string id, bool install) {
  if (String.IsNullOrEmpty(id) || !id.StartsWith(@"USB\VID_3251&PID_1930\", StringComparison.OrdinalIgnoreCase))
   throw new ArgumentException("Expected an exact Aurora 930 device instance ID.");
  IntPtr set=SetupDiCreateDeviceInfoList(IntPtr.Zero,IntPtr.Zero);
  if(set==new IntPtr(-1)) throw new Win32Exception(Marshal.GetLastWin32Error());
  try {
   var dev=new Device(); dev.cbSize=(uint)Marshal.SizeOf(dev);
   Check(SetupDiOpenDeviceInfo(set,id,IntPtr.Zero,0,ref dev),"Open Aurora device");
   var p=new Params(); p.cbSize=(uint)Marshal.SizeOf(p);
   Check(SetupDiGetDeviceInstallParams(set,ref dev,ref p),"Get install parameters");
   p.Flags|=0x10000; p.FlagsEx|=0x800; p.DriverPath=Environment.GetFolderPath(Environment.SpecialFolder.Windows)+@"\INF\winusb.inf";
   Check(SetupDiSetDeviceInstallParams(set,ref dev,ref p),"Set inbox INF path");
   Check(SetupDiBuildDriverInfoList(set,ref dev,1),"Enumerate inbox drivers");
   for(uint i=0;;i++) {
    var d=new Driver(); d.cbSize=(uint)Marshal.SizeOf(d);
    if(!SetupDiEnumDriverInfo(set,ref dev,1,i,ref d)) break;
    if(d.Description=="WinUsb Device" && d.ProviderName=="Microsoft") {
     if(!install) return "Available signed inbox driver: "+d.Description+" / "+d.ProviderName;
     bool reboot;
     Check(DiInstallDevice(IntPtr.Zero,set,ref dev,ref d,0,out reboot),"Install signed inbox WinUSB");
     return "Installed Microsoft inbox WinUSB. Reboot required: "+reboot;
    }
   }
   throw new Exception("Microsoft WinUsb Device node not found; no device changes made.");
  } finally { SetupDiDestroyDeviceInfoList(set); }
 }
}
