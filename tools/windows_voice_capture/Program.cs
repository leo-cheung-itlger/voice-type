using System.Text;
using System.Text.Json;
using Windows.Devices.Enumeration;
using Windows.Media;
using Windows.Media.Capture;
using Windows.Media.MediaProperties;
using Windows.Storage;

Console.OutputEncoding = Encoding.UTF8;

static Dictionary<string, string> ParseArgs(string[] args)
{
    var values = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
    for (var i = 0; i < args.Length; i++)
    {
        var arg = args[i];
        if (!arg.StartsWith("--", StringComparison.Ordinal)) continue;
        var key = arg[2..];
        var value = "true";
        if (key.Contains('='))
        {
            var parts = key.Split('=', 2);
            key = parts[0];
            value = parts[1];
        }
        else if (i + 1 < args.Length && !args[i + 1].StartsWith("--", StringComparison.Ordinal))
        {
            value = args[++i];
        }
        values[key] = value;
    }
    return values;
}

static MediaCategory ParseCategory(string value)
{
    return value.Trim().ToLowerInvariant() switch
    {
        "voicetyping" => MediaCategory.VoiceTyping,
        "uniformspeech" => MediaCategory.UniformSpeech,
        "speech" => MediaCategory.Speech,
        "communications" => MediaCategory.Communications,
        "farfieldspeech" => MediaCategory.FarFieldSpeech,
        _ => MediaCategory.VoiceTyping,
    };
}

static AudioProcessing ParseProcessing(string value)
{
    return value.Trim().ToLowerInvariant() switch
    {
        "raw" => AudioProcessing.Raw,
        "default" => AudioProcessing.Default,
        _ => AudioProcessing.Default,
    };
}

static string Json(object value) => JsonSerializer.Serialize(value, new JsonSerializerOptions
{
    WriteIndented = false,
});

static async Task<DeviceInformation?> SelectDevice(string preferredName)
{
    var devices = await DeviceInformation.FindAllAsync(DeviceClass.AudioCapture);
    if (devices.Count == 0) return null;
    if (!string.IsNullOrWhiteSpace(preferredName))
    {
        var lowered = preferredName.ToLowerInvariant();
        foreach (var device in devices)
        {
            if (device.Name.ToLowerInvariant().Contains(lowered) || lowered.Contains(device.Name.ToLowerInvariant()))
            {
                return device;
            }
        }
    }
    return devices[0];
}

static async Task<int> RunAsync(string[] args)
{
    var parsed = ParseArgs(args);
    if (!parsed.TryGetValue("output", out var output) || string.IsNullOrWhiteSpace(output))
    {
        Console.Error.WriteLine("Missing --output");
        return 2;
    }

    var seconds = 5.0;
    if (parsed.TryGetValue("seconds", out var secondsValue))
    {
        double.TryParse(secondsValue, out seconds);
    }
    seconds = Math.Clamp(seconds <= 0 ? 5.0 : seconds, 0.5, 30.0);

    var categoryName = parsed.GetValueOrDefault("category", "VoiceTyping");
    var processingName = parsed.GetValueOrDefault("processing", "Default");
    var deviceName = parsed.GetValueOrDefault("device-name", "");
    var waitForStdin = parsed.ContainsKey("wait-for-stdin");
    var category = ParseCategory(categoryName);
    var processing = ParseProcessing(processingName);

    var outputPath = Path.GetFullPath(output);
    Directory.CreateDirectory(Path.GetDirectoryName(outputPath)!);
    if (File.Exists(outputPath)) File.Delete(outputPath);

    var selectedDevice = await SelectDevice(deviceName);
    if (selectedDevice is null)
    {
        Console.Error.WriteLine("No audio capture device found");
        return 3;
    }

    var folder = await StorageFolder.GetFolderFromPathAsync(Path.GetDirectoryName(outputPath)!);
    var file = await folder.CreateFileAsync(Path.GetFileName(outputPath), CreationCollisionOption.ReplaceExisting);

    var settings = new MediaCaptureInitializationSettings
    {
        StreamingCaptureMode = StreamingCaptureMode.Audio,
        MediaCategory = category,
        AudioProcessing = processing,
        AudioDeviceId = selectedDevice.Id,
    };

    using var capture = new MediaCapture();
    await capture.InitializeAsync(settings);

    var profile = MediaEncodingProfile.CreateWav(AudioEncodingQuality.Auto);
    profile.Audio = AudioEncodingProperties.CreatePcm(16000, 1, 16);

    await capture.StartRecordToStorageFileAsync(profile, file);
    if (waitForStdin)
    {
        await Console.In.ReadLineAsync();
    }
    else
    {
        await Task.Delay(TimeSpan.FromSeconds(seconds));
    }
    await capture.StopRecordAsync();

    var info = new
    {
        ok = true,
        output = outputPath,
        seconds,
        wait_for_stdin = waitForStdin,
        device = new
        {
            id = selectedDevice.Id,
            name = selectedDevice.Name,
        },
        media_category = category.ToString(),
        audio_processing = processing.ToString(),
        sample_rate = 16000,
        channels = 1,
        bits_per_sample = 16,
    };
    Console.WriteLine(Json(info));
    return 0;
}

var exitCode = 1;
Exception? failure = null;
var thread = new Thread(() =>
{
    try
    {
        exitCode = RunAsync(args).GetAwaiter().GetResult();
    }
    catch (Exception ex)
    {
        failure = ex;
        exitCode = 1;
    }
});
thread.SetApartmentState(ApartmentState.STA);
thread.Start();
thread.Join();

if (failure is not null)
{
    Console.Error.WriteLine(failure.ToString());
}

return exitCode;
