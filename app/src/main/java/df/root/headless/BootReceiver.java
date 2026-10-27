package df.root.headless;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.util.Log;
import java.io.File;

public class BootReceiver extends BroadcastReceiver {
    private static final String TAG = "DFRoot_Boot";
    private static final String FLAG_SUCCESS = "/data/local/tmp/dfroot_success.flag";
    private static final String FLAG_FAIL = "/data/local/tmp/dfroot_fail.flag";

    @Override
    public void onReceive(Context context, Intent intent) {
        String action = intent != null ? intent.getAction() : null;
        if (Intent.ACTION_BOOT_COMPLETED.equals(action) || Intent.ACTION_LOCKED_BOOT_COMPLETED.equals(action)) {
            Log.i(TAG, "Boot detected, reset flags");
            // clear stale session flags
            new File(FLAG_SUCCESS).delete();
            new File(FLAG_FAIL).delete();
        }
    }
}
