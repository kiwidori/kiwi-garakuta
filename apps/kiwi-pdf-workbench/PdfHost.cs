using System;
using System.IO;
using System.Text;
using System.Runtime.InteropServices;

class PdfHost
{
    [DllImport("qpdf30.dll", CallingConvention = CallingConvention.Cdecl, ExactSpelling = true)]
    static extern int qpdfjob_run_from_json(IntPtr json);

    static int Main()
    {
        Console.OutputEncoding = new UTF8Encoding(false);
        byte[] payload = null;
        IntPtr ptr = IntPtr.Zero;
        try
        {
            using (Stream input = Console.OpenStandardInput())
            using (MemoryStream buffer = new MemoryStream())
            {
                byte[] chunk = new byte[8192];
                int read;
                while ((read = input.Read(chunk, 0, chunk.Length)) > 0)
                {
                    if (buffer.Length + read > 2 * 1024 * 1024) return 2;
                    buffer.Write(chunk, 0, read);
                }
                payload = buffer.ToArray();
            }
            ptr = Marshal.AllocHGlobal(payload.Length + 1);
            Marshal.Copy(payload, 0, ptr, payload.Length);
            Marshal.WriteByte(ptr, payload.Length, 0);
            return qpdfjob_run_from_json(ptr);
        }
        catch (Exception)
        {
            Console.Error.WriteLine("エラーが発生しました。");
            return 2;
        }
        finally
        {
            if (ptr != IntPtr.Zero)
            {
                for (int i = 0; i < payload.Length + 1; i++) Marshal.WriteByte(ptr, i, 0);
                Marshal.FreeHGlobal(ptr);
            }
            if (payload != null) Array.Clear(payload, 0, payload.Length);
        }
    }
}
