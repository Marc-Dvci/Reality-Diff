package app.realitydiff;

import android.content.ContentResolver;
import android.content.Context;
import android.database.Cursor;
import android.net.Uri;
import android.provider.OpenableColumns;

import java.io.BufferedInputStream;
import java.io.BufferedOutputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.UUID;

final class RealityDiffApiClient {
    private static final int MAX_BATCH = 12;
    private static final int BUFFER_SIZE = 64 * 1024;

    boolean isConfigured() {
        return !BuildConfig.API_BASE_URL.trim().isEmpty();
    }

    int uploadUris(Context context, List<Uri> uris, String source) throws IOException {
        if (!isConfigured()) throw new IOException("Reality Diff API URL is not configured");
        List<Uri> supported = new ArrayList<>();
        for (Uri uri : uris) {
            if (mediaType(context.getContentResolver(), uri) != null) supported.add(uri);
        }
        int uploaded = 0;
        for (int start = 0; start < supported.size(); start += MAX_BATCH) {
            int end = Math.min(supported.size(), start + MAX_BATCH);
            uploadBatch(context, supported.subList(start, end), source);
            uploaded += end - start;
        }
        return uploaded;
    }

    private void uploadBatch(Context context, List<Uri> uris, String source) throws IOException {
        String boundary = "RealityDiff-" + UUID.randomUUID();
        URL endpoint = new URL(trimSlash(BuildConfig.API_BASE_URL) + "/api/v1/media/analyze");
        HttpURLConnection connection = (HttpURLConnection) endpoint.openConnection();
        connection.setRequestMethod("POST");
        connection.setDoOutput(true);
        connection.setConnectTimeout(15_000);
        connection.setReadTimeout(300_000);
        connection.setChunkedStreamingMode(BUFFER_SIZE);
        connection.setRequestProperty("Accept", "application/json");
        connection.setRequestProperty("Content-Type", "multipart/form-data; boundary=" + boundary);

        try (DataOutputStream output = new DataOutputStream(
                new BufferedOutputStream(connection.getOutputStream(), BUFFER_SIZE))) {
            writeTextPart(output, boundary, "source", source);
            for (Uri uri : uris) writeImagePart(context, output, boundary, uri);
            output.writeBytes("--" + boundary + "--\r\n");
        }

        int status = connection.getResponseCode();
        try (InputStream response = status >= 400
                ? connection.getErrorStream()
                : connection.getInputStream()) {
            if (response != null) {
                byte[] responseBuffer = new byte[4096];
                while (response.read(responseBuffer) != -1) { /* Drain for reuse. */ }
            }
        } finally {
            connection.disconnect();
        }
        if (status < 200 || status >= 300) throw new IOException("Reality Diff API returned " + status);
    }

    private static void writeTextPart(
            DataOutputStream output, String boundary, String name, String value
    ) throws IOException {
        output.writeBytes("--" + boundary + "\r\n");
        output.writeBytes("Content-Disposition: form-data; name=\"" + name + "\"\r\n\r\n");
        output.write(value.getBytes(StandardCharsets.UTF_8));
        output.writeBytes("\r\n");
    }

    private static void writeImagePart(
            Context context, DataOutputStream output, String boundary, Uri uri
    ) throws IOException {
        ContentResolver resolver = context.getContentResolver();
        String mimeType = mediaType(resolver, uri);
        if (mimeType == null) throw new IOException("Unsupported image format");
        String filename = safeFilename(displayName(resolver, uri));
        output.writeBytes("--" + boundary + "\r\n");
        output.writeBytes(
                "Content-Disposition: form-data; name=\"files\"; filename=\""
                        + filename + "\"\r\n"
        );
        output.writeBytes("Content-Type: " + mimeType + "\r\n\r\n");
        InputStream rawInput = resolver.openInputStream(uri);
        if (rawInput == null) throw new IOException("The selected photo could not be opened");
        try (InputStream input = new BufferedInputStream(rawInput, BUFFER_SIZE)) {
            byte[] buffer = new byte[BUFFER_SIZE];
            int read;
            while ((read = input.read(buffer)) != -1) output.write(buffer, 0, read);
        }
        output.writeBytes("\r\n");
    }

    private static String displayName(ContentResolver resolver, Uri uri) {
        try (Cursor cursor = resolver.query(
                uri, new String[]{OpenableColumns.DISPLAY_NAME}, null, null, null)) {
            if (cursor != null && cursor.moveToFirst()) {
                int index = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME);
                if (index >= 0) return cursor.getString(index);
            }
        }
        return "android-photo.jpg";
    }

    private static String safeFilename(String filename) {
        return filename.replace("\r", "").replace("\n", "").replace("\"", "'");
    }

    private static String mediaType(ContentResolver resolver, Uri uri) {
        String value = resolver.getType(uri);
        if (value != null) value = value.toLowerCase(Locale.ROOT);
        if (List.of("image/jpeg", "image/png", "image/webp").contains(value)) return value;
        String name = displayName(resolver, uri).toLowerCase(Locale.ROOT);
        if (name.endsWith(".jpg") || name.endsWith(".jpeg")) return "image/jpeg";
        if (name.endsWith(".png")) return "image/png";
        if (name.endsWith(".webp")) return "image/webp";
        return null;
    }

    private static String trimSlash(String value) {
        return value.endsWith("/") ? value.substring(0, value.length() - 1) : value;
    }
}
