package df.root.headless;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.os.Build;
import android.os.IBinder;
import android.util.Log;
import java.io.BufferedInputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.FileWriter;
import java.io.IOException;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;
import df.root.ExploitRunner;
import df.root.IReporter;

public class RootService extends Service implements IReporter {
    private static final String TAG = "DFRoot_Headless";
    private static final String CHANNEL_ID = "dfroot_headless";
    private static final int NOTIF_ID = 2026;
    private static final String FLAG_SUCCESS = "/data/local/tmp/dfroot_success.flag";
    private static final String FLAG_FAIL = "/data/local/tmp/dfroot_fail.flag";
    private static final String LOG_PATH = "/data/local/tmp/dfroot.log";
    private static final String LOCAL_APK = "/data/local/tmp/ksu.apk";
    private static final String KSU_URL = "https://github.com/KernelSU-Next/KernelSU-Next/releases/download/v3.4.1/KernelSU_Next_v3.4.1_33333-release.apk";
    private Context mDeCtx;

    @Override
    public void onCreate() {
        super.onCreate();
        mDeCtx = createDeviceProtectedStorageContext();
        createNotificationChannel();
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        report("RootService started\n");
        // check success flag
        if (new File(FLAG_SUCCESS).exists()) {
            if (new File("/dev/df").exists()) {
                report("Already rooted in current session, exiting\n");
                stopSelf();
                return START_NOT_STICKY;
            }
            report("Stale flag detected from previous session, resetting\n");
            new File(FLAG_SUCCESS).delete();
            new File(FLAG_FAIL).delete();
        }
        // start foreground service
        startForeground(NOTIF_ID, buildNotification());
        new Thread(this::doRootWorkflow).start();
        return START_NOT_STICKY;
    }

    private void doRootWorkflow() {
        try {
            report("Preparing assets\n");
            File deDir = mDeCtx.getFilesDir().getParentFile();
            if (deDir == null || (!deDir.exists() && !deDir.mkdirs())) {
                throw new IOException("Cannot access DE dir");
            }
            File ksudTarget = new File(deDir, "ksud");
            if (!ksudTarget.exists() || ksudTarget.length() == 0) {
                boolean extracted = extractFromApk(new File(LOCAL_APK), ksudTarget);
                if (!extracted) {
                    report("Downloading fallback APK\n");
                    File downloaded = downloadFallbackApk();
                    extracted = extractFromApk(downloaded, ksudTarget);
                    if (downloaded.exists()) downloaded.delete();
                }
                if (!extracted) throw new IOException("libksud.so extraction failed");
            }
            ksudTarget.setExecutable(true, false);
            report("Assets ready\n");
            // execute exploit
            int rc = ExploitRunner.run(mDeCtx, this);
            report("Exploit exited: " + rc + "\n");
            boolean success = (rc == 0) || new File("/dev/df").exists() || new File("/data/adb/ksud").exists();
            if (success) {
                writeFlag(FLAG_SUCCESS, "SUCCESS\n");
                new File(FLAG_FAIL).delete();
                report("Root success\n");
            } else {
                writeFlag(FLAG_FAIL, "FAILED: " + rc + "\n");
                report("Root failed\n");
            }
        } catch (Throwable t) {
            Log.e(TAG, "Root error", t);
            report("Exception: " + t.getMessage() + "\n");
            writeFlag(FLAG_FAIL, "EXCEPTION: " + t + "\n");
        } finally {
            stopForeground(true);
            stopSelf();
        }
    }

    private boolean extractFromApk(File apkFile, File targetFile) {
        if (!apkFile.exists() || !apkFile.canRead()) return false;
        try (ZipInputStream zis = new ZipInputStream(new BufferedInputStream(new FileInputStream(apkFile)))) {
            ZipEntry entry;
            while ((entry = zis.getNextEntry()) != null) {
                if ("lib/arm64-v8a/libksud.so".equals(entry.getName())) {
                    try (FileOutputStream fos = new FileOutputStream(targetFile)) {
                        byte[] buf = new byte[16384];
                        int n;
                        while ((n = zis.read(buf)) != -1) fos.write(buf, 0, n);
                        fos.flush();
                    }
                    targetFile.setExecutable(true, false);
                    return true;
                }
            }
        } catch (Exception e) {
            report("Extract error: " + e.getMessage() + "\n");
        }
        return false;
    }

    private File downloadFallbackApk() throws IOException {
        File cacheApk = new File(getCacheDir(), "ksu_tmp.apk");
        if (cacheApk.exists()) cacheApk.delete();
        String targetUrl = KSU_URL;
        for (int i = 0; i < 5; i++) {
            HttpURLConnection conn = (HttpURLConnection) new URL(targetUrl).openConnection();
            conn.setConnectTimeout(15000);
            conn.setReadTimeout(30000);
            conn.setInstanceFollowRedirects(false);
            int code = conn.getResponseCode();
            if (code == HttpURLConnection.HTTP_MOVED_TEMP || code == HttpURLConnection.HTTP_MOVED_PERM || code == 307 || code == 308) {
                String loc = conn.getHeaderField("Location");
                conn.disconnect();
                if (loc == null) throw new IOException("Redirect missing location");
                targetUrl = loc;
                continue;
            }
            if (code != HttpURLConnection.HTTP_OK) {
                conn.disconnect();
                throw new IOException("Download HTTP error: " + code);
            }
            try (InputStream in = new BufferedInputStream(conn.getInputStream());
                 FileOutputStream out = new FileOutputStream(cacheApk)) {
                byte[] buf = new byte[16384];
                int n;
                while ((n = in.read(buf)) != -1) out.write(buf, 0, n);
                out.flush();
            } finally {
                conn.disconnect();
            }
            break;
        }
        return cacheApk;
    }

    private void writeFlag(String path, String content) {
        try {
            File f = new File(path);
            try (FileWriter fw = new FileWriter(f, false)) { fw.write(content); }
            f.setReadable(true, false);
            f.setWritable(true, false);
        } catch (Exception ignored) {}
    }

    private void createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationChannel ch = new NotificationChannel(CHANNEL_ID, "DFRoot", NotificationManager.IMPORTANCE_MIN);
            NotificationManager nm = (NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE);
            if (nm != null) nm.createNotificationChannel(ch);
        }
    }

    private Notification buildNotification() {
        Notification.Builder b = (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) ?
                new Notification.Builder(this, CHANNEL_ID) : new Notification.Builder(this);
        return b.setContentTitle("DFRoot Headless")
                .setContentText("Executing root...")
                .setSmallIcon(android.R.drawable.ic_dialog_info)
                .setOngoing(true)
                .build();
    }

    @Override
    public void report(String msg) {
        Log.i(TAG, msg.trim());
        try {
            File logFile = new File(LOG_PATH);
            try (FileWriter fw = new FileWriter(logFile, true)) { fw.write(msg); }
        } catch (Exception ignored) {}
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }
}
