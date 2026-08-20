package app.realitydiff;

import java.util.Locale;

final class DemoReasoner {
    static final class Answer {
        final String title;
        final String text;
        final String confidence;
        final boolean uncertain;

        Answer(String title, String text, String confidence, boolean uncertain) {
            this.title = title;
            this.text = text;
            this.confidence = confidence;
            this.uncertain = uncertain;
        }
    }

    Answer answer(String question) {
        String query = question.toLowerCase(Locale.ROOT);
        if (query.contains("chair")) return new Answer(
                "Your chair changed between June 4 and June 11",
                "The dark mesh chair is last clearly visible on June 4. The sand-coloured ergonomic chair first appears on June 11. There is no usable workspace photo between those dates, so the evidence supports a seven-day window—not a single day.",
                "96% · high confidence", false);
        if (hasDamageWord(query) && !hasRegion(query)) return new Answer(
                "Which mark do you mean?",
                "I found a front-left bumper scuff and a rear-right bumper scratch. Their pickup coverage is different, so I should not choose one for you.",
                "clarification required", true);
        if (hasDamageWord(query) && (query.contains("rear") || query.contains("right"))) return new Answer(
                "I can’t determine whether it was already there",
                "The rear-right scratch is visible at return, but no pickup photo clearly shows that bumper region. An unseen area is not evidence that the mark was new.",
                "18% · missing pickup view", true);
        if (hasDamageWord(query)) return new Answer(
                "Yes—the front-left scuff was visible at pickup",
                "The same short horizontal scuff appears on August 3 and August 8 at the same bumper position.",
                "97% · high confidence", false);
        if (query.contains("bike") || query.contains("bicycle") || query.contains("project")) return new Answer(
                "Five restoration stages reconstructed",
                "Documented → stripped → prepared → repainted → reassembled. Preparation is first clear on March 1 and completion first appears on May 29.",
                "91% · high confidence", false);
        return new Answer(
                "Try a recurring physical subject",
                "I could not connect that question to supported observations. Ask about the home office, the white rental car, or the blue bike project.",
                "no matching evidence", true);
    }

    private static boolean hasDamageWord(String query) {
        return query.contains("scratch") || query.contains("scuff") || query.contains("mark") || query.contains("damage");
    }

    private static boolean hasRegion(String query) {
        return query.contains("front") || query.contains("rear") || query.contains("left") || query.contains("right") || query.contains("bumper");
    }
}
