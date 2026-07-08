package com.rehabcoach.btapp.model;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

public class RehabResult {
    public String recordId = "";
    public String recordType = "";
    public int recordIndex = 0;
    public int completion = 0;
    public double totalScore;
    public String level = "";
    public String levelName = "";
    public String source = "";
    public String advice = "";
    public String summaryText = "";
    public String statusText = "";
    public String timestampText = "";
    public final LinkedHashMap<String, Double> dimensionScores = new LinkedHashMap<>();
    public final List<String> actionNames = new ArrayList<>();
    public final List<Double> actionScores = new ArrayList<>();

    public boolean hasScore() {
        return totalScore > 0.0 || !dimensionScores.isEmpty() || !level.isEmpty();
    }

    public boolean isTrainingRecord() {
        String type = recordType == null ? "" : recordType.trim().toLowerCase(Locale.US);
        String src = source == null ? "" : source.trim().toLowerCase(Locale.US);
        return "training".equals(type) || src.contains("training");
    }

    public boolean isAssessmentRecord() {
        String type = recordType == null ? "" : recordType.trim().toLowerCase(Locale.US);
        String src = source == null ? "" : source.trim().toLowerCase(Locale.US);
        return "assessment".equals(type)
                || src.contains("assessment")
                || src.contains("medical")
                || (!isTrainingRecord() && (!dimensionScores.isEmpty() || !advice.isEmpty()));
    }

    public String identityKey() {
        if (recordId != null && !recordId.trim().isEmpty()) {
            return recordId.trim();
        }
        String type = recordType == null ? "" : recordType.trim();
        String time = timestampText == null ? "" : timestampText.trim();
        String src = source == null ? "" : source.trim();
        String adviceKey = advice == null ? "" : advice.trim();
        if (adviceKey.length() > 24) {
            adviceKey = adviceKey.substring(0, 24);
        }
        return type + "|" + recordIndex + "|" + time + "|" + src + "|"
                + String.format(Locale.US, "%.2f", totalScore) + "|" + adviceKey;
    }

    public String displayLevel() {
        if (levelName != null && !levelName.trim().isEmpty()) {
            return levelName;
        }
        String normalized = level == null ? "" : level.trim().toUpperCase(Locale.US);
        if (normalized.length() == 1 && Character.isDigit(normalized.charAt(0))) {
            normalized = "L" + normalized;
        }
        switch (normalized) {
            case "L1":
                return "L1 保护辅助";
            case "L2":
                return "L2 基础恢复";
            case "L3":
                return "L3 稳定提升";
            case "L4":
                return "L4 巩固痊愈";
            default:
                if (!normalized.isEmpty()) {
                    return normalized;
                }
                return "未评估";
        }
    }

    public String displaySource() {
        if ("training".equalsIgnoreCase(source)) {
            return "训练结果";
        }
        if ("assessment".equalsIgnoreCase(source) || "imu_dual_measure".equalsIgnoreCase(source)) {
            return "初评结果";
        }
        if (source != null && !source.trim().isEmpty()) {
            return source;
        }
        return "RK3588 数据";
    }

    public static String dimensionName(String key) {
        if (key == null) {
            return "未知维度";
        }
        switch (key) {
            case "range_of_motion":
                return "抬举幅度";
            case "smoothness":
                return "运动平滑";
            case "tremor":
                return "震颤程度";
            case "symmetry":
                return "双侧对称";
            case "speed":
                return "运动速度";
            case "endurance":
            case "fatigue":
                return "运动耐力";
            default:
                if (key.startsWith("block_")) {
                    return "训练动作 " + key.substring("block_".length());
                }
                return key;
        }
    }

    public static double dimensionMaxPoints(String key) {
        if ("range_of_motion".equals(key)) {
            return 30.0;
        }
        if ("smoothness".equals(key)) {
            return 25.0;
        }
        if ("tremor".equals(key)) {
            return 20.0;
        }
        if ("symmetry".equals(key)) {
            return 15.0;
        }
        if ("speed".equals(key) || "endurance".equals(key) || "fatigue".equals(key)) {
            return 5.0;
        }
        return 100.0;
    }

    public static int dimensionPercent(String key, double rawValue) {
        double percent;
        if (rawValue <= 1.0) {
            percent = rawValue * 100.0;
        } else {
            double maxPoints = dimensionMaxPoints(key);
            if (maxPoints > 0.0 && rawValue <= maxPoints + 0.01) {
                percent = rawValue / maxPoints * 100.0;
            } else {
                percent = rawValue;
            }
        }
        return Math.max(0, Math.min(100, (int) Math.round(percent)));
    }

    public static String dimensionValueLabel(String key, double rawValue) {
        int percent = dimensionPercent(key, rawValue);
        double maxPoints = dimensionMaxPoints(key);
        if (rawValue > 1.0 && maxPoints < 100.0 && rawValue <= maxPoints + 0.01) {
            return String.format(Locale.CHINA, "%.1f/%.0f 分 · %d%%", rawValue, maxPoints, percent);
        }
        return String.format(Locale.CHINA, "%d%%", percent);
    }

    public static String autoAdvice(double score) {
        if (score >= 81.0) {
            return "当前康复表现较好，建议继续保持规律训练，重点巩固动作稳定性、左右对称性和耐力；训练后若出现明显疼痛、肿胀或麻木，应暂停并咨询专业人员。";
        }
        if (score >= 61.0) {
            return "当前处于稳定提升阶段，建议在安全范围内逐步增加动作质量要求，优先保证慢起慢落、姿势正确和训练后的疲劳可恢复。";
        }
        if (score >= 40.0) {
            return "当前仍需加强基础恢复，建议降低动作难度，从无痛范围内的小幅度、多组短时训练开始，并记录疼痛和疲劳变化。";
        }
        return "当前得分偏低，建议先暂停高强度训练，在医生或康复治疗师指导下确认训练方案；若伴随明显疼痛、麻木、无力或活动范围突然下降，请及时就医评估。";
    }

    public static String dimensionSuggestion(String key, int percent) {
        String name = dimensionName(key);
        if (percent >= 80) {
            return name + "表现较好，继续维持动作标准和稳定节奏。";
        }
        if (percent >= 50) {
            return name + "仍有提升空间，建议降低速度，优先练习可控制的小幅动作。";
        }
        return name + "偏低，建议减少负荷并结合疼痛、疲劳和传感器佩戴情况复查。";
    }

    public Map<String, Double> dimensionsInDisplayOrder() {
        LinkedHashMap<String, Double> ordered = new LinkedHashMap<>();
        String[] keys = {
                "range_of_motion", "smoothness", "tremor",
                "symmetry", "speed", "endurance", "fatigue"
        };
        for (String key : keys) {
            if (dimensionScores.containsKey(key)) {
                ordered.put(key, dimensionScores.get(key));
            }
        }
        for (Map.Entry<String, Double> entry : dimensionScores.entrySet()) {
            if (!ordered.containsKey(entry.getKey())) {
                ordered.put(entry.getKey(), entry.getValue());
            }
        }
        return ordered;
    }

    public JSONObject toJson() throws JSONException {
        JSONObject object = new JSONObject();
        object.put("record_id", recordId);
        object.put("record_type", recordType);
        object.put("record_index", recordIndex);
        object.put("completion", completion);
        object.put("total_score", totalScore);
        object.put("level", level);
        object.put("level_name", levelName);
        object.put("source", source);
        object.put("advice", advice);
        object.put("summary_text", summaryText);
        object.put("status_text", statusText);
        object.put("timestamp_text", timestampText);

        JSONObject dims = new JSONObject();
        for (Map.Entry<String, Double> entry : dimensionScores.entrySet()) {
            dims.put(entry.getKey(), entry.getValue());
        }
        object.put("dimension_scores", dims);

        JSONArray names = new JSONArray();
        for (String name : actionNames) {
            names.put(name);
        }
        object.put("action_names", names);

        JSONArray scores = new JSONArray();
        for (Double score : actionScores) {
            scores.put(score == null ? 0.0 : score);
        }
        object.put("action_scores", scores);
        return object;
    }

    public static RehabResult fromJson(JSONObject object) {
        RehabResult result = new RehabResult();
        if (object == null) {
            return result;
        }
        result.recordId = optStringAny(object, "record_id", "recordId");
        result.recordType = optStringAny(object, "record_type", "recordType");
        result.recordIndex = object.optInt("record_index", object.optInt("recordIndex", 0));
        result.completion = object.optInt("completion", 0);
        result.totalScore = optDoubleAny(object, "total_score", "compositeScore", "session_score");
        result.level = optStringAny(object, "level");
        result.levelName = optStringAny(object, "level_name", "levelName");
        result.source = optStringAny(object, "source");
        result.advice = optStringAny(object, "advice", "summary_text");
        result.summaryText = optStringAny(object, "summary_text", "summaryText");
        result.statusText = optStringAny(object, "status_text", "statusText", "note");
        result.timestampText = optStringAny(object, "timestamp_text", "timestampText", "timestamp", "csv_time");

        JSONObject dims = object.optJSONObject("dimension_scores");
        if (dims == null) {
            dims = object.optJSONObject("dims");
        }
        if (dims != null) {
            java.util.Iterator<String> keys = dims.keys();
            while (keys.hasNext()) {
                String key = keys.next();
                result.dimensionScores.put(key, dims.optDouble(key, 0.0));
            }
        }

        JSONArray names = object.optJSONArray("action_names");
        if (names == null) {
            names = object.optJSONArray("blockNames");
        }
        if (names != null) {
            for (int i = 0; i < names.length(); i++) {
                String name = names.optString(i, "");
                if (!name.trim().isEmpty()) {
                    result.actionNames.add(name);
                }
            }
        }

        JSONArray scores = object.optJSONArray("action_scores");
        if (scores == null) {
            scores = object.optJSONArray("blockScores");
        }
        if (scores != null) {
            for (int i = 0; i < scores.length(); i++) {
                result.actionScores.add(scores.optDouble(i, 0.0));
            }
        }
        return result;
    }

    private static double optDoubleAny(JSONObject object, String... keys) {
        for (String key : keys) {
            if (object.has(key) && !object.isNull(key)) {
                return object.optDouble(key, 0.0);
            }
        }
        return 0.0;
    }

    private static String optStringAny(JSONObject object, String... keys) {
        for (String key : keys) {
            if (!object.has(key) || object.isNull(key)) {
                continue;
            }
            String value = object.optString(key, "");
            if (!value.trim().isEmpty() && !"null".equalsIgnoreCase(value.trim())) {
                return value;
            }
        }
        return "";
    }
}
