package app.realitydiff;

import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.os.Bundle;
import android.text.InputType;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.EditText;
import android.widget.HorizontalScrollView;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.Space;
import android.widget.TextView;
import android.widget.Toast;

import androidx.activity.ComponentActivity;
import androidx.activity.result.ActivityResultLauncher;
import androidx.activity.result.PickVisualMediaRequest;
import androidx.activity.result.contract.ActivityResultContracts;
import androidx.core.graphics.Insets;
import androidx.core.view.ViewCompat;
import androidx.core.view.WindowCompat;
import androidx.core.view.WindowInsetsCompat;

import java.io.IOException;
import java.io.InputStream;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class MainActivity extends ComponentActivity {
    private static final int BG = Color.rgb(248, 250, 253);
    private static final int SURFACE = Color.WHITE;
    private static final int SURFACE_2 = Color.rgb(240, 244, 249);
    private static final int INK = Color.rgb(31, 31, 31);
    private static final int MUTED = Color.rgb(95, 99, 104);
    private static final int LINE = Color.rgb(217, 226, 238);
    private static final int VIOLET = Color.rgb(11, 87, 208);
    private static final int VIOLET_SOFT = Color.rgb(211, 227, 253);
    private static final int MINT = Color.rgb(24, 128, 56);
    private static final int MINT_SOFT = Color.rgb(230, 244, 234);
    private static final int AMBER = Color.rgb(176, 96, 0);
    private static final int AMBER_SOFT = Color.rgb(254, 247, 224);

    private DemoWorld world;
    private final DemoReasoner reasoner = new DemoReasoner();
    private final ExecutorService imageExecutor = Executors.newFixedThreadPool(2);
    private MediaLibraryConnector mediaConnector;
    private final RealityDiffApiClient apiClient = new RealityDiffApiClient();
    private ActivityResultLauncher<String> libraryPermissionLauncher;
    private ActivityResultLauncher<PickVisualMediaRequest> photoPickerLauncher;
    private LinearLayout content;
    private final List<Button> navButtons = new ArrayList<>();

    @Override protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        WindowCompat.enableEdgeToEdge(getWindow());
        registerResultLaunchers();
        world = DemoWorld.load(this);
        mediaConnector = new MediaLibraryConnector(this);
        setContentView(buildShell());
        showHome();
    }

    private void registerResultLaunchers() {
        libraryPermissionLauncher = registerForActivityResult(
                new ActivityResultContracts.RequestPermission(),
                granted -> {
                    if (granted) countLibrary();
                    else Toast.makeText(
                            this,
                            "Library access was not granted. The private Photo Picker is still available.",
                            Toast.LENGTH_LONG
                    ).show();
                }
        );
        photoPickerLauncher = registerForActivityResult(
                new ActivityResultContracts.PickMultipleVisualMedia(50),
                uris -> {
                    if (uris.isEmpty()) return;
                    mediaConnector.retainSelections(uris);
                    if (!apiClient.isConfigured()) {
                        Toast.makeText(
                                this,
                                uris.size() + " selected photo" + (uris.size() == 1 ? "" : "s")
                                        + " retained; configure REALITYDIFF_API_BASE_URL to sync",
                                Toast.LENGTH_LONG
                        ).show();
                        return;
                    }
                    Toast.makeText(this, "Sending selected photos to Reality Diff…", Toast.LENGTH_SHORT).show();
                    imageExecutor.execute(() -> {
                        try {
                            int uploaded = apiClient.uploadUris(this, uris, "android_picker");
                            runOnUiThread(() -> Toast.makeText(
                                    this,
                                    uploaded + " supported photo" + (uploaded == 1 ? "" : "s")
                                            + " submitted to Gemini",
                                    Toast.LENGTH_LONG
                            ).show());
                        } catch (IOException error) {
                            runOnUiThread(() -> Toast.makeText(
                                    this,
                                    "Sync paused; selections are retained for retry",
                                    Toast.LENGTH_LONG
                            ).show());
                        }
                    });
                }
        );
    }

    private View buildShell() {
        LinearLayout root = column();
        root.setBackgroundColor(BG);
        ViewCompat.setOnApplyWindowInsetsListener(root, (view, windowInsets) -> {
            Insets insets = windowInsets.getInsets(
                    WindowInsetsCompat.Type.systemBars() | WindowInsetsCompat.Type.displayCutout()
            );
            view.setPadding(insets.left, insets.top, insets.right, insets.bottom);
            return windowInsets;
        });
        root.addView(buildHeader(), matchWrap());

        ScrollView scroll = new ScrollView(this);
        scroll.setFillViewport(true);
        scroll.setClipToPadding(false);
        content = column();
        content.setPadding(dp(18), dp(24), dp(18), dp(34));
        scroll.addView(content, matchWrap());
        root.addView(scroll, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1));
        root.addView(buildBottomNavigation(), matchWrap());
        return root;
    }

    private View buildHeader() {
        LinearLayout header = row();
        header.setGravity(Gravity.CENTER_VERTICAL);
        header.setPadding(dp(18), dp(10), dp(12), dp(10));
        header.setBackgroundColor(SURFACE);

        ImageView logo = new ImageView(this);
        logo.setImageResource(R.drawable.ic_launcher);
        logo.setContentDescription(null);
        header.addView(logo, new LinearLayout.LayoutParams(dp(36), dp(36)));

        LinearLayout names = column();
        names.setPadding(dp(10), 0, 0, 0);
        names.addView(label("Reality Diff", 16, INK, Typeface.BOLD), wrapWrap());
        TextView subtitle = label("WITH GEMINI", 9, MUTED, Typeface.BOLD);
        subtitle.setLetterSpacing(.12f);
        names.addView(subtitle, wrapWrap());
        header.addView(names, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1));

        TextView demo = label("●  SAMPLE WORLD", 9, AMBER, Typeface.BOLD);
        demo.setPadding(dp(10), dp(7), dp(10), dp(7));
        demo.setBackground(roundRect(SURFACE_2, 999, LINE, 1));
        header.addView(demo, wrapWrap());
        return header;
    }

    private View buildBottomNavigation() {
        LinearLayout nav = row();
        nav.setGravity(Gravity.CENTER);
        nav.setPadding(dp(6), dp(6), dp(6), dp(8));
        nav.setBackground(roundRect(SURFACE, 0, LINE, 1));
        navButtons.add(navButton("Home", this::showHome));
        navButtons.add(navButton("Reality", this::showReality));
        navButtons.add(navButton("Ask", this::showAsk));
        navButtons.add(navButton("Sources", this::showSources));
        for (Button button : navButtons) nav.addView(button, new LinearLayout.LayoutParams(0, dp(50), 1));
        return nav;
    }

    private Button navButton(String text, Runnable action) {
        Button button = new Button(this);
        button.setAllCaps(false);
        button.setText(text);
        button.setTextSize(11);
        button.setTextColor(MUTED);
        button.setGravity(Gravity.CENTER);
        button.setMinWidth(0);
        button.setMinimumWidth(0);
        button.setPadding(dp(3), 0, dp(3), 0);
        button.setBackground(roundRect(Color.TRANSPARENT, 11, Color.TRANSPARENT, 0));
        button.setOnClickListener(view -> action.run());
        return button;
    }

    private void selectNav(int index) {
        for (int i = 0; i < navButtons.size(); i++) {
            Button button = navButtons.get(i);
            boolean selected = i == index;
            button.setTextColor(selected ? VIOLET : MUTED);
            button.setTypeface(Typeface.DEFAULT, selected ? Typeface.BOLD : Typeface.NORMAL);
            button.setBackground(roundRect(selected ? VIOLET_SOFT : Color.TRANSPARENT, 11, Color.TRANSPARENT, 0));
        }
    }

    private void reset(int navigationIndex) {
        content.removeAllViews();
        selectNav(navigationIndex);
    }

    private void showHome() {
        reset(0);
        eyebrow(content, "YOUR WORLD · RECONSTRUCTED");
        TextView title = label("Photos remember moments.\nReality Diff remembers state.", 35, INK, Typeface.BOLD);
        title.setLetterSpacing(-.025f);
        title.setLineSpacing(0, .94f);
        content.addView(title, matchWrap());
        paragraph(content, "Ask what changed, when it changed, and what the original photographs actually prove.");

        LinearLayout actions = row();
        actions.setPadding(0, dp(18), 0, dp(18));
        actions.addView(actionButton("Ask your world", true, this::showAsk), new LinearLayout.LayoutParams(0, dp(48), 1));
        Space gap = new Space(this);
        actions.addView(gap, new LinearLayout.LayoutParams(dp(9), 1));
        actions.addView(actionButton("Explore realities", false, this::showReality), new LinearLayout.LayoutParams(0, dp(48), 1));
        content.addView(actions, matchWrap());

        DemoWorld.Subject office = world.subject("home-office");
        ImageView hero = photo(dp(228), office.cover, "Current home office state");
        hero.setBackground(roundRect(SURFACE_2, 20, LINE, 1));
        content.addView(hero, matchHeight(dp(228)));
        TextView change = label("CHANGE DETECTED  ·  Monitor upgraded", 10, Color.WHITE, Typeface.BOLD);
        change.setPadding(dp(12), dp(9), dp(12), dp(9));
        change.setBackground(roundRect(Color.rgb(67, 60, 55), 10, Color.TRANSPARENT, 0));
        LinearLayout.LayoutParams changeParams = wrapWrap();
        changeParams.setMargins(dp(12), -dp(53), 0, dp(17));
        content.addView(change, changeParams);

        LinearLayout stats = row();
        stats.setPadding(dp(4), dp(3), dp(4), dp(3));
        stats.setBackground(roundRect(SURFACE, 15, LINE, 1));
        stats.addView(stat(String.valueOf(world.photosIndexed), "photos"), new LinearLayout.LayoutParams(0, dp(70), 1));
        stats.addView(stat(String.valueOf(world.subjects.size()), "realities"), new LinearLayout.LayoutParams(0, dp(70), 1));
        stats.addView(stat(String.valueOf(world.supportedChanges), "changes"), new LinearLayout.LayoutParams(0, dp(70), 1));
        content.addView(stats, matchWrap());

        sectionTitle(content, "Reality, organised", dp(30));
        content.addView(subjectScroller(), matchWrap());

        LinearLayout ask = column();
        ask.setPadding(dp(20), dp(20), dp(20), dp(20));
        ask.setBackground(roundRect(INK, 18, Color.TRANSPARENT, 0));
        ask.addView(label("What do you want to remember?", 19, Color.WHITE, Typeface.BOLD), matchWrap());
        TextView askCopy = label("Answers are bounded by photo evidence. Missing views stay missing.", 12, Color.rgb(190, 187, 180), Typeface.NORMAL);
        askCopy.setPadding(0, dp(7), 0, dp(14));
        ask.addView(askCopy, matchWrap());
        ask.addView(actionButton("Ask Reality Diff  →", false, this::showAsk), matchHeight(dp(44)));
        LinearLayout.LayoutParams askParams = matchWrap();
        askParams.setMargins(0, dp(30), 0, 0);
        content.addView(ask, askParams);
    }

    private View subjectScroller() {
        HorizontalScrollView horizontal = new HorizontalScrollView(this);
        horizontal.setHorizontalScrollBarEnabled(false);
        horizontal.setClipToPadding(false);
        LinearLayout cards = row();
        for (DemoWorld.Subject subject : world.subjects) {
            View card = subjectCard(subject);
            LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(dp(230), dp(265));
            params.setMargins(0, 0, dp(12), 0);
            cards.addView(card, params);
        }
        horizontal.addView(cards, wrapWrap());
        return horizontal;
    }

    private View subjectCard(DemoWorld.Subject subject) {
        LinearLayout card = column();
        card.setPadding(dp(10), dp(10), dp(10), dp(13));
        card.setBackground(roundRect(SURFACE, 16, LINE, 1));
        card.setClickable(true);
        card.setFocusable(true);
        card.setContentDescription("Open " + subject.name + ", " + subject.photoCount + " photos");
        card.setOnClickListener(view -> showSubject(subject));
        card.addView(photo(dp(145), subject.cover, null), matchHeight(dp(145)));
        TextView name = label(subject.name, 15, INK, Typeface.BOLD);
        name.setPadding(dp(2), dp(12), dp(2), 0);
        card.addView(name, matchWrap());
        TextView summary = label(subject.summary, 10, MUTED, Typeface.NORMAL);
        summary.setMaxLines(2);
        summary.setPadding(dp(2), dp(5), dp(2), 0);
        card.addView(summary, matchWrap());
        TextView meta = label(subject.photoCount + " photos  ·  " + Math.round(subject.confidence * 100) + "% match", 9, MINT, Typeface.BOLD);
        meta.setPadding(dp(2), dp(9), dp(2), 0);
        card.addView(meta, matchWrap());
        return card;
    }

    private void showReality() {
        reset(1);
        eyebrow(content, "SEMANTIC WORLD");
        content.addView(label("Your realities", 34, INK, Typeface.BOLD), matchWrap());
        paragraph(content, "Recurring places, objects and projects discovered across ordinary photos—not manually created albums.");
        for (DemoWorld.Subject subject : world.subjects) {
            View card = wideSubjectCard(subject);
            LinearLayout.LayoutParams params = matchHeight(dp(132));
            params.setMargins(0, 0, 0, dp(12));
            content.addView(card, params);
        }
        TextView privacy = label("Discovery, not surveillance. Only photos you connect are indexed, and every subject can be disconnected or deleted.", 11, AMBER, Typeface.NORMAL);
        privacy.setPadding(dp(15), dp(13), dp(15), dp(13));
        privacy.setBackground(roundRect(AMBER_SOFT, 12, Color.rgb(231, 217, 174), 1));
        content.addView(privacy, matchWrap());
    }

    private View wideSubjectCard(DemoWorld.Subject subject) {
        LinearLayout card = row();
        card.setGravity(Gravity.CENTER_VERTICAL);
        card.setPadding(dp(9), dp(9), dp(12), dp(9));
        card.setBackground(roundRect(SURFACE, 16, LINE, 1));
        ImageView image = photo(dp(112), subject.cover, null);
        card.addView(image, new LinearLayout.LayoutParams(dp(112), dp(112)));
        LinearLayout copy = column();
        copy.setPadding(dp(14), 0, 0, 0);
        copy.addView(label(subject.name, 16, INK, Typeface.BOLD), matchWrap());
        TextView description = label(subject.summary, 11, MUTED, Typeface.NORMAL);
        description.setPadding(0, dp(6), 0, dp(7));
        description.setMaxLines(3);
        copy.addView(description, matchWrap());
        copy.addView(label(subject.photoCount + " photos · " + subject.changes.size() + " changes", 9, MINT, Typeface.BOLD), matchWrap());
        card.addView(copy, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1));
        card.setOnClickListener(view -> showSubject(subject));
        card.setClickable(true);
        card.setFocusable(true);
        return card;
    }

    private void showSubject(DemoWorld.Subject subject) {
        reset(1);
        Button back = textButton("←  All realities", this::showReality);
        content.addView(back, wrapWrap());
        ImageView cover = photo(dp(250), subject.cover, subject.name);
        LinearLayout.LayoutParams coverParams = matchHeight(dp(250));
        coverParams.setMargins(0, dp(10), 0, dp(18));
        content.addView(cover, coverParams);
        eyebrow(content, subject.kind.toUpperCase(Locale.ROOT) + " · " + Math.round(subject.confidence * 100) + "% IDENTITY MATCH");
        content.addView(label(subject.name, 32, INK, Typeface.BOLD), matchWrap());
        paragraph(content, subject.summary + " " + subject.photoCount + " photos · " + subject.range + ".");
        sectionTitle(content, subject.kind.equals("project") ? "Project stages" : "Change history", dp(25));
        for (DemoWorld.Change change : subject.changes) content.addView(changeRow(change), matchWrap());

        LinearLayout coverage = column();
        coverage.setPadding(dp(16), dp(15), dp(16), dp(15));
        coverage.setBackground(roundRect(MINT_SOFT, 14, Color.TRANSPARENT, 0));
        coverage.addView(label("EVIDENCE COVERAGE", 9, MINT, Typeface.BOLD), matchWrap());
        String note = subject.id.equals("white-rental-car")
                ? "72% · Pickup set has no clear rear-right bumper view."
                : subject.id.equals("home-office")
                ? "88% · No usable workspace photo from June 5–10."
                : "84% · Strong stage coverage; paint curing was not photographed.";
        TextView noteView = label(note, 12, INK, Typeface.NORMAL);
        noteView.setPadding(0, dp(7), 0, 0);
        coverage.addView(noteView, matchWrap());
        LinearLayout.LayoutParams coverageParams = matchWrap();
        coverageParams.setMargins(0, dp(18), 0, dp(16));
        content.addView(coverage, coverageParams);
        Button ask = actionButton("Ask about " + subject.name, true, this::showAsk);
        content.addView(ask, matchHeight(dp(48)));
    }

    private View changeRow(DemoWorld.Change change) {
        LinearLayout row = column();
        row.setPadding(dp(15), dp(14), dp(15), dp(14));
        boolean unknown = change.type.equals("UNVERIFIABLE");
        row.setBackground(roundRect(unknown ? AMBER_SOFT : SURFACE, 13, unknown ? Color.rgb(231, 217, 174) : LINE, 1));
        row.addView(label(change.type.replace('_', ' '), 8, unknown ? AMBER : VIOLET, Typeface.BOLD), matchWrap());
        TextView title = label(change.title, 14, INK, Typeface.BOLD);
        title.setPadding(0, dp(6), 0, dp(4));
        row.addView(title, matchWrap());
        row.addView(label(change.when + " · " + Math.round(change.confidence * 100) + "% confidence", 10, MUTED, Typeface.NORMAL), matchWrap());
        LinearLayout.LayoutParams params = matchWrap();
        params.setMargins(0, 0, 0, dp(9));
        row.setLayoutParams(params);
        return row;
    }

    private void showAsk() {
        reset(2);
        eyebrow(content, "COLLABORATIVE PARTNER");
        content.addView(label("Ask your physical history", 32, INK, Typeface.BOLD), matchWrap());
        paragraph(content, "Every factual answer can be opened back to its source photographs.");

        LinearLayout agent = column();
        agent.setPadding(dp(16), dp(15), dp(16), dp(15));
        agent.setBackground(roundRect(VIOLET_SOFT, 14, Color.TRANSPARENT, 0));
        agent.addView(label("Reality Diff", 13, VIOLET, Typeface.BOLD), matchWrap());
        TextView hello = label("What do you want to know? I can explain an evidence-backed change or tell you when a necessary view is missing.", 12, INK, Typeface.NORMAL);
        hello.setPadding(0, dp(7), 0, 0);
        agent.addView(hello, matchWrap());
        content.addView(agent, matchWrap());

        sectionTitle(content, "Try a real question", dp(24));
        addPrompt("When did I replace my chair?");
        addPrompt("Was this scratch already there?");
        addPrompt("Was the rear-right scratch already there at pickup?");
        addPrompt("Show me how the bike restoration evolved.");

        EditText input = new EditText(this);
        input.setHint("Ask when something changed…");
        input.setTextSize(13);
        input.setTextColor(INK);
        input.setHintTextColor(MUTED);
        input.setSingleLine(false);
        input.setMaxLines(4);
        input.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_CAP_SENTENCES | InputType.TYPE_TEXT_FLAG_MULTI_LINE);
        input.setPadding(dp(14), dp(12), dp(14), dp(12));
        input.setBackground(roundRect(SURFACE, 12, LINE, 1));
        LinearLayout.LayoutParams inputParams = matchHeight(dp(74));
        inputParams.setMargins(0, dp(22), 0, dp(9));
        content.addView(input, inputParams);
        content.addView(actionButton("Ask Reality Diff  →", true, () -> {
            String question = input.getText().toString().trim();
            if (question.isEmpty()) input.setError("Ask a question first");
            else showAnswer(question);
        }), matchHeight(dp(48)));
    }

    private void addPrompt(String question) {
        Button prompt = textButton(question + "   ›", () -> showAnswer(question));
        prompt.setGravity(Gravity.START | Gravity.CENTER_VERTICAL);
        prompt.setPadding(dp(13), 0, dp(13), 0);
        prompt.setBackground(roundRect(SURFACE, 11, LINE, 1));
        LinearLayout.LayoutParams params = matchHeight(dp(52));
        params.setMargins(0, 0, 0, dp(8));
        content.addView(prompt, params);
    }

    private void showAnswer(String question) {
        reset(2);
        Button back = textButton("←  Ask another question", this::showAsk);
        content.addView(back, wrapWrap());
        TextView user = label(question, 13, Color.WHITE, Typeface.NORMAL);
        user.setPadding(dp(14), dp(12), dp(14), dp(12));
        user.setBackground(roundRect(INK, 14, Color.TRANSPARENT, 0));
        LinearLayout.LayoutParams userParams = wrapWrap();
        userParams.gravity = Gravity.END;
        userParams.setMargins(dp(40), dp(20), 0, dp(14));
        content.addView(user, userParams);

        DemoReasoner.Answer answer = reasoner.answer(question);
        LinearLayout card = column();
        card.setPadding(dp(17), dp(16), dp(17), dp(16));
        card.setBackground(roundRect(answer.uncertain ? AMBER_SOFT : VIOLET_SOFT, 15, Color.TRANSPARENT, 0));
        card.addView(label(answer.title, 18, INK, Typeface.BOLD), matchWrap());
        TextView text = label(answer.text, 13, INK, Typeface.NORMAL);
        text.setLineSpacing(dp(3), 1);
        text.setPadding(0, dp(9), 0, dp(13));
        card.addView(text, matchWrap());
        TextView confidence = label(answer.confidence, 10, answer.uncertain ? AMBER : MINT, Typeface.BOLD);
        confidence.setPadding(dp(9), dp(6), dp(9), dp(6));
        confidence.setBackground(roundRect(answer.uncertain ? Color.rgb(255, 247, 222) : MINT_SOFT, 999, Color.TRANSPARENT, 0));
        card.addView(confidence, wrapWrap());
        LinearLayout.LayoutParams cardParams = matchWrap();
        cardParams.setMargins(0, 0, dp(18), dp(16));
        content.addView(card, cardParams);

        LinearLayout trust = column();
        trust.setPadding(dp(15), dp(14), dp(15), dp(14));
        trust.setBackground(roundRect(SURFACE, 13, LINE, 1));
        trust.addView(label("WHY THIS ANSWER", 9, VIOLET, Typeface.BOLD), matchWrap());
        TextView trace = label("1  Resolved the physical entity\n2  Retrieved before and after observations\n3  Checked region coverage and contradictions\n4  Returned the narrowest supported claim", 11, MUTED, Typeface.NORMAL);
        trace.setLineSpacing(dp(6), 1);
        trace.setPadding(0, dp(9), 0, 0);
        trust.addView(trace, matchWrap());
        content.addView(trust, matchWrap());
    }

    private void showSources() {
        reset(3);
        eyebrow(content, "INPUTS AND AGENT ACTIVITY");
        content.addView(label("Connect your photos", 32, INK, Typeface.BOLD), matchWrap());
        paragraph(content, "Use the full local gallery for automatic indexing, or Android's private Photo Picker for selected media—including eligible cloud photos.");

        sourceAction("Use my photo library", "Automatic incremental MediaStore indexing", mediaConnector.hasLibraryAccess() ? "Connected" : "Permission required", () -> {
            if (mediaConnector.hasLibraryAccess()) countLibrary();
            else libraryPermissionLauncher.launch(mediaConnector.libraryPermission());
        });
        sourceAction("Choose specific photos", "Android system Photo Picker; no full-library grant", "Private selection", () ->
                photoPickerLauncher.launch(
                        new PickVisualMediaRequest.Builder()
                                .setMediaType(ActivityResultContracts.PickVisualMedia.ImageOnly.INSTANCE)
                                .build()
                )
        );
        sourceAction("Not now", "Keep exploring the synthetic judge dataset", "No permission needed", () -> Toast.makeText(this, "Demo data remains available offline", Toast.LENGTH_SHORT).show());

        sectionTitle(content, "Background pipeline", dp(28));
        String[] stages = {"Discover new media", "Deduplicate cheaply", "Gemini 3.5 Flash-Lite triage", "Gemini 3.7 Flash reasoning", "Gemini Embedding 2 retrieval", "Google ADK world memory"};
        for (int i = 0; i < stages.length; i++) {
            TextView stage = label(String.format(Locale.ROOT, "%02d   %s", i + 1, stages[i]), 12, i < 2 ? MINT : VIOLET, Typeface.BOLD);
            stage.setPadding(dp(14), dp(13), dp(14), dp(13));
            stage.setBackground(roundRect(SURFACE, 11, LINE, 1));
            LinearLayout.LayoutParams params = matchWrap();
            params.setMargins(0, 0, 0, dp(7));
            content.addView(stage, params);
        }

        TextView honesty = label("Sample boundary: evidence sequences are synthetic and fixed for repeatable evaluation. When an API URL is configured, Photo Picker and MediaStore images are privately uploaded and analyzed by the live Google model pipeline.", 11, AMBER, Typeface.NORMAL);
        honesty.setPadding(dp(15), dp(14), dp(15), dp(14));
        honesty.setBackground(roundRect(AMBER_SOFT, 12, Color.rgb(231, 217, 174), 1));
        LinearLayout.LayoutParams honestyParams = matchWrap();
        honestyParams.setMargins(0, dp(18), 0, 0);
        content.addView(honesty, honestyParams);
    }

    private void sourceAction(String title, String subtitle, String status, Runnable action) {
        LinearLayout card = column();
        card.setPadding(dp(16), dp(14), dp(16), dp(14));
        card.setBackground(roundRect(SURFACE, 14, LINE, 1));
        card.addView(label(title, 15, INK, Typeface.BOLD), matchWrap());
        TextView description = label(subtitle, 11, MUTED, Typeface.NORMAL);
        description.setPadding(0, dp(5), 0, dp(8));
        card.addView(description, matchWrap());
        card.addView(label(status + "  →", 10, VIOLET, Typeface.BOLD), matchWrap());
        card.setClickable(true);
        card.setFocusable(true);
        card.setOnClickListener(view -> action.run());
        LinearLayout.LayoutParams params = matchWrap();
        params.setMargins(0, 0, 0, dp(10));
        content.addView(card, params);
    }

    private void countLibrary() {
        Toast.makeText(this, "Reading the MediaStore index…", Toast.LENGTH_SHORT).show();
        mediaConnector.countImages(count -> {
            mediaConnector.scheduleIncrementalSync();
            Toast.makeText(this, count + " accessible photos discovered; background sync scheduled", Toast.LENGTH_LONG).show();
            showSources();
        });
    }

    @Override protected void onDestroy() {
        mediaConnector.close();
        imageExecutor.shutdownNow();
        super.onDestroy();
    }

    private ImageView photo(int height, String path, String description) {
        ImageView image = new ImageView(this);
        image.setScaleType(ImageView.ScaleType.CENTER_CROP);
        image.setContentDescription(description);
        image.setBackgroundColor(SURFACE_2);
        setAssetImage(image, path, height);
        return image;
    }

    private void setAssetImage(ImageView target, String path, int targetHeight) {
        imageExecutor.execute(() -> {
            try (InputStream boundsStream = getAssets().open(path)) {
                BitmapFactory.Options bounds = new BitmapFactory.Options();
                bounds.inJustDecodeBounds = true;
                BitmapFactory.decodeStream(boundsStream, null, bounds);
                int sample = 1;
                int desired = Math.max(dp(260), targetHeight * 2);
                while (bounds.outHeight / sample > desired * 2) sample *= 2;
                BitmapFactory.Options options = new BitmapFactory.Options();
                options.inSampleSize = sample;
                options.inPreferredConfig = Bitmap.Config.RGB_565;
                try (InputStream imageStream = getAssets().open(path)) {
                    Bitmap bitmap = BitmapFactory.decodeStream(imageStream, null, options);
                    if (bitmap != null) runOnUiThread(() -> target.setImageBitmap(bitmap));
                }
            } catch (IOException ignored) {
                // The semantic card remains legible with its neutral placeholder.
            }
        });
    }

    private View stat(String value, String caption) {
        LinearLayout stat = column();
        stat.setGravity(Gravity.CENTER);
        stat.addView(label(value, 20, INK, Typeface.BOLD), wrapWrap());
        stat.addView(label(caption, 9, MUTED, Typeface.NORMAL), wrapWrap());
        return stat;
    }

    private void eyebrow(LinearLayout parent, String value) {
        TextView text = label(value, 9, VIOLET, Typeface.BOLD);
        text.setLetterSpacing(.11f);
        LinearLayout.LayoutParams params = matchWrap();
        params.setMargins(0, 0, 0, dp(10));
        parent.addView(text, params);
    }

    private void paragraph(LinearLayout parent, String value) {
        TextView text = label(value, 14, MUTED, Typeface.NORMAL);
        text.setLineSpacing(dp(3), 1);
        LinearLayout.LayoutParams params = matchWrap();
        params.setMargins(0, dp(11), 0, 0);
        parent.addView(text, params);
    }

    private void sectionTitle(LinearLayout parent, String value, int topMargin) {
        TextView title = label(value, 19, INK, Typeface.BOLD);
        LinearLayout.LayoutParams params = matchWrap();
        params.setMargins(0, topMargin, 0, dp(13));
        parent.addView(title, params);
    }

    private Button actionButton(String text, boolean primary, Runnable action) {
        Button button = new Button(this);
        button.setText(text);
        button.setAllCaps(false);
        button.setTextSize(12);
        button.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        button.setTextColor(primary ? Color.WHITE : INK);
        button.setGravity(Gravity.CENTER);
        button.setPadding(dp(10), 0, dp(10), 0);
        button.setMinHeight(0);
        button.setMinimumHeight(0);
        button.setBackground(roundRect(primary ? VIOLET : SURFACE, 12, primary ? VIOLET : LINE, 1));
        button.setOnClickListener(view -> action.run());
        return button;
    }

    private Button textButton(String text, Runnable action) {
        Button button = new Button(this);
        button.setText(text);
        button.setAllCaps(false);
        button.setTextSize(11);
        button.setTextColor(VIOLET);
        button.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        button.setMinHeight(0);
        button.setMinimumHeight(0);
        button.setMinWidth(0);
        button.setMinimumWidth(0);
        button.setPadding(0, 0, 0, 0);
        button.setBackgroundColor(Color.TRANSPARENT);
        button.setOnClickListener(view -> action.run());
        return button;
    }

    private TextView label(String value, int sp, int color, int style) {
        TextView text = new TextView(this);
        text.setText(value);
        text.setTextSize(sp);
        text.setTextColor(color);
        text.setTypeface(Typeface.DEFAULT, style);
        text.setIncludeFontPadding(false);
        return text;
    }

    private LinearLayout column() {
        LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.VERTICAL);
        return layout;
    }

    private LinearLayout row() {
        LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.HORIZONTAL);
        return layout;
    }

    private GradientDrawable roundRect(int fill, int radiusDp, int stroke, int strokeDp) {
        GradientDrawable drawable = new GradientDrawable();
        drawable.setColor(fill);
        drawable.setCornerRadius(dp(radiusDp));
        if (strokeDp > 0) drawable.setStroke(dp(strokeDp), stroke);
        return drawable;
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }

    private static LinearLayout.LayoutParams matchWrap() {
        return new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
    }

    private static LinearLayout.LayoutParams wrapWrap() {
        return new LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT);
    }

    private static LinearLayout.LayoutParams matchHeight(int height) {
        return new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, height);
    }
}
