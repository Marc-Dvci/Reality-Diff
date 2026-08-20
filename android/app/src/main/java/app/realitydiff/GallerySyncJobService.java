package app.realitydiff;

import android.app.job.JobParameters;
import android.app.job.JobService;
import android.content.SharedPreferences;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.List;
import java.util.stream.Collectors;

public final class GallerySyncJobService extends JobService {
    private final ExecutorService executor = Executors.newSingleThreadExecutor();

    @Override public boolean onStartJob(JobParameters params) {
        executor.execute(() -> {
            int currentCount = MediaLibraryConnector.queryImageCount(this);
            SharedPreferences preferences = getSharedPreferences("reality_diff_sync", MODE_PRIVATE);
            int previousCount = preferences.getInt("media_count", 0);
            RealityDiffApiClient api = new RealityDiffApiClient();
            if (!api.isConfigured()) {
                saveScan(preferences, currentCount, previousCount);
                jobFinished(params, false);
                return;
            }
            long cursor = preferences.getLong("last_media_added_seconds", 0L);
            long cursorId = preferences.getLong("last_media_id", 0L);
            List<MediaCandidate> media = MediaLibraryConnector.queryNewImages(
                    this, cursor, cursorId, 12
            );
            if (media.isEmpty()) {
                saveScan(preferences, currentCount, previousCount);
                jobFinished(params, false);
                return;
            }
            try {
                api.uploadUris(
                        this,
                        media.stream().map(item -> item.uri).collect(Collectors.toList()),
                        "android_mediastore"
                );
                MediaCandidate latest = media.get(media.size() - 1);
                preferences.edit()
                        .putLong("last_media_added_seconds", latest.addedAtSeconds)
                        .putLong("last_media_id", latest.mediaId)
                        .apply();
                saveScan(preferences, currentCount, previousCount);
                jobFinished(params, media.size() == 12);
            } catch (Exception error) {
                jobFinished(params, true);
            }
        });
        return true;
    }

    @Override public boolean onStopJob(JobParameters params) {
        executor.shutdownNow();
        return true;
    }

    private static void saveScan(
            SharedPreferences preferences, int currentCount, int previousCount
    ) {
        preferences.edit()
                .putInt("media_count", currentCount)
                .putInt("new_media_count", Math.max(0, currentCount - previousCount))
                .putLong("last_scan_at", System.currentTimeMillis())
                .apply();
    }
}
