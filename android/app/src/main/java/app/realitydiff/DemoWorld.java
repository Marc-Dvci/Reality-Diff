package app.realitydiff;

import android.content.Context;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

final class DemoWorld {
    static final class Subject {
        final String id;
        final String name;
        final String kind;
        final String cover;
        final int photoCount;
        final String range;
        final String summary;
        final double confidence;
        final List<Change> changes;

        Subject(JSONObject source) throws JSONException {
            id = source.getString("id");
            name = source.getString("name");
            kind = source.getString("kind");
            cover = trimAssetPrefix(source.getString("cover"));
            photoCount = source.getInt("photo_count");
            range = source.getString("range");
            summary = source.getString("summary");
            confidence = source.getDouble("confidence");
            changes = new ArrayList<>();
            JSONArray rawChanges = source.getJSONArray("changes");
            for (int i = 0; i < rawChanges.length(); i++) changes.add(new Change(rawChanges.getJSONObject(i)));
        }
    }

    static final class Change {
        final String type;
        final String title;
        final String when;
        final double confidence;

        Change(JSONObject source) throws JSONException {
            type = source.getString("type");
            title = source.getString("title");
            when = source.getString("when");
            confidence = source.getDouble("confidence");
        }
    }

    final List<Subject> subjects;
    final int photosIndexed;
    final int supportedChanges;

    private DemoWorld(List<Subject> subjects, int photosIndexed, int supportedChanges) {
        this.subjects = Collections.unmodifiableList(subjects);
        this.photosIndexed = photosIndexed;
        this.supportedChanges = supportedChanges;
    }

    Subject subject(String id) {
        for (Subject subject : subjects) if (subject.id.equals(id)) return subject;
        return subjects.get(0);
    }

    static DemoWorld load(Context context) {
        try {
            StringBuilder content = new StringBuilder();
            try (BufferedReader reader = new BufferedReader(new InputStreamReader(
                    context.getAssets().open("fixtures/demo.json"), StandardCharsets.UTF_8))) {
                String line;
                while ((line = reader.readLine()) != null) content.append(line);
            }
            JSONObject root = new JSONObject(content.toString());
            JSONObject summary = root.getJSONObject("summary");
            JSONArray rawSubjects = root.getJSONArray("subjects");
            List<Subject> subjects = new ArrayList<>();
            for (int i = 0; i < rawSubjects.length(); i++) subjects.add(new Subject(rawSubjects.getJSONObject(i)));
            return new DemoWorld(subjects, summary.getInt("photos_indexed"), summary.getInt("changes"));
        } catch (IOException | JSONException error) {
            throw new IllegalStateException("Bundled Reality Diff fixture is invalid", error);
        }
    }

    private static String trimAssetPrefix(String value) {
        return value.startsWith("/") ? value.substring(1) : value;
    }
}
