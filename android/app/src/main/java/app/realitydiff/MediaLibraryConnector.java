package app.realitydiff;

import android.Manifest;
import android.app.job.JobInfo;
import android.app.job.JobScheduler;
import android.content.ComponentName;
import android.content.ContentResolver;
import android.content.ContentUris;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.database.Cursor;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.provider.MediaStore;

import androidx.activity.ComponentActivity;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.function.IntConsumer;

final class MediaLibraryConnector {
    private final ComponentActivity activity;
    private final ExecutorService executor = Executors.newSingleThreadExecutor();

    MediaLibraryConnector(ComponentActivity activity) {
        this.activity = activity;
    }

    String libraryPermission() {
        return Build.VERSION.SDK_INT >= 33
                ? Manifest.permission.READ_MEDIA_IMAGES
                : Manifest.permission.READ_EXTERNAL_STORAGE;
    }

    boolean hasLibraryAccess() {
        String permission = Build.VERSION.SDK_INT >= 33
                ? Manifest.permission.READ_MEDIA_IMAGES
                : Manifest.permission.READ_EXTERNAL_STORAGE;
        return activity.checkSelfPermission(permission) == PackageManager.PERMISSION_GRANTED;
    }

    void countImages(IntConsumer callback) {
        executor.execute(() -> {
            int count = queryImageCount(activity);
            activity.runOnUiThread(() -> callback.accept(count));
        });
    }

    void retainSelections(List<Uri> uris) {
        if (Build.VERSION.SDK_INT >= 33) return;
        for (Uri uri : uris) retainSelection(uri);
    }

    private void retainSelection(Uri uri) {
        if (uri == null) return;
        try { activity.getContentResolver().takePersistableUriPermission(uri, Intent.FLAG_GRANT_READ_URI_PERMISSION); }
        catch (SecurityException ignored) { /* Provider grants may be session-only. */ }
    }

    void scheduleIncrementalSync() {
        JobScheduler scheduler = activity.getSystemService(JobScheduler.class);
        if (scheduler == null) return;
        JobInfo job = new JobInfo.Builder(RealityDiffJobs.GALLERY_SYNC,
                new ComponentName(activity, GallerySyncJobService.class))
                .setPersisted(false)
                .setRequiredNetworkType(JobInfo.NETWORK_TYPE_ANY)
                .setPeriodic(6L * 60L * 60L * 1000L)
                .build();
        scheduler.schedule(job);
    }

    static int queryImageCount(Context context) {
        String[] projection = new String[]{MediaStore.Images.Media._ID};
        try (Cursor cursor = context.getContentResolver().query(
                MediaStore.Images.Media.EXTERNAL_CONTENT_URI,
                projection, null, null, null)) {
            return cursor == null ? 0 : cursor.getCount();
        } catch (SecurityException error) {
            return 0;
        }
    }

    static List<MediaCandidate> queryNewImages(
            Context context, long afterSeconds, long afterId, int limit
    ) {
        List<MediaCandidate> result = new ArrayList<>();
        String[] projection = new String[]{
                MediaStore.Images.Media._ID,
                MediaStore.Images.Media.DATE_ADDED,
                MediaStore.Images.Media.MIME_TYPE,
        };
        Bundle arguments = new Bundle();
        arguments.putString(
                ContentResolver.QUERY_ARG_SQL_SELECTION,
                "(" + MediaStore.Images.Media.DATE_ADDED + " > ? OR ("
                        + MediaStore.Images.Media.DATE_ADDED + " = ? AND "
                        + MediaStore.Images.Media._ID + " > ?)) AND "
                        + MediaStore.Images.Media.MIME_TYPE + " IN (?, ?, ?)"
        );
        arguments.putStringArray(
                ContentResolver.QUERY_ARG_SQL_SELECTION_ARGS,
                new String[]{
                        String.valueOf(afterSeconds),
                        String.valueOf(afterSeconds),
                        String.valueOf(afterId),
                        "image/jpeg",
                        "image/png",
                        "image/webp",
                }
        );
        arguments.putString(
                ContentResolver.QUERY_ARG_SQL_SORT_ORDER,
                MediaStore.Images.Media.DATE_ADDED + " ASC, "
                        + MediaStore.Images.Media._ID + " ASC"
        );
        arguments.putInt(ContentResolver.QUERY_ARG_LIMIT, limit);
        try (Cursor cursor = context.getContentResolver().query(
                MediaStore.Images.Media.EXTERNAL_CONTENT_URI,
                projection,
                arguments,
                null)) {
            if (cursor == null) return result;
            int idColumn = cursor.getColumnIndexOrThrow(MediaStore.Images.Media._ID);
            int dateColumn = cursor.getColumnIndexOrThrow(MediaStore.Images.Media.DATE_ADDED);
            while (cursor.moveToNext()) {
                long id = cursor.getLong(idColumn);
                result.add(new MediaCandidate(
                        ContentUris.withAppendedId(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, id),
                        cursor.getLong(dateColumn),
                        id
                ));
            }
        } catch (SecurityException ignored) {
            // The next run can retry after the user grants or expands access.
        }
        return result;
    }

    void close() { executor.shutdownNow(); }
}

final class MediaCandidate {
    final Uri uri;
    final long addedAtSeconds;
    final long mediaId;

    MediaCandidate(Uri uri, long addedAtSeconds, long mediaId) {
        this.uri = uri;
        this.addedAtSeconds = addedAtSeconds;
        this.mediaId = mediaId;
    }
}

final class RealityDiffJobs {
    static final int GALLERY_SYNC = 0x5244;
    private RealityDiffJobs() {}
}
