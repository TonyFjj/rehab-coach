package com.rehabcoach.btapp.model;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Date;
import java.util.Iterator;
import java.util.List;
import java.util.Locale;

public final class RehabMessageParser {
    private RehabMessageParser() {
    }

    public static class ParsedMessage {
        public RehabResult result;
        public final List<RehabResult> results = new ArrayList<>();
        public String status;
        public String rawType;
    }

    public static ParsedMessage parse(String line) throws JSONException {
        JSONObject root = new JSONObject(line);
        ParsedMessage parsed = new ParsedMessage();
        parsed.rawType = root.optString("type", root.optString("event", "unknown"));

        String type = root.optString("type", "");
        if ("sync_snapshot".equals(type) || "records_snapshot".equals(type)) {
            JSONObject payload = root.optJSONObject("payload");
            if (payload == null) {
                payload = root;
            }
            readRecordArray(payload.optJSONArray("training_records"), "training", parsed.results);
            readRecordArray(payload.optJSONArray("assessment_records"), "assessment", parsed.results);
            readRecordArray(payload.optJSONArray("medical_advice_records"), "assessment", parsed.results);
            parsed.status = "收到同步记录 " + parsed.results.size() + " 条";
            return parsed;
        }

        if ("training_record".equals(type) || "assessment_record".equals(type) || "medical_advice_record".equals(type)) {
            JSONObject payload = root.optJSONObject("payload");
            if (payload == null) {
                payload = root;
            }
            parsed.result = "training_record".equals(type)
                    ? parseTrainingRecord(payload)
                    : parseAssessmentRecord(payload);
            return parsed;
        }

        if ("scoring".equals(type) || "rehab_summary".equals(type)) {
            JSONObject payload = root.optJSONObject("payload");
            if (payload == null) {
                payload = root;
            }
            parsed.result = parseScoringPayload(payload, root.optDouble("timestamp", 0.0));
            return parsed;
        }

        if ("session_summary".equals(type)) {
            JSONObject payload = root.optJSONObject("payload");
            RehabResult result = new RehabResult();
            result.advice = payload == null ? "" : payload.optString("summary_text", "");
            result.summaryText = result.advice;
            result.timestampText = timestampText(root.optDouble("timestamp", 0.0));
            parsed.result = result;
            parsed.status = "收到训练总结";
            return parsed;
        }

        if ("system_status".equals(type) || "training_state".equals(type) || "training_progress".equals(type)) {
            JSONObject payload = root.optJSONObject("payload");
            parsed.status = payload == null ? type : payload.toString();
            return parsed;
        }

        if ("assessment_result".equals(root.optString("event", ""))) {
            parsed.result = parseScoringPayload(root, root.optDouble("timestamp", 0.0));
            return parsed;
        }

        JSONObject latest = root.optJSONObject("latestAssessment");
        if (latest != null) {
            parsed.result = parseQtStoredResult(latest);
            return parsed;
        }

        if (root.has("total_score") || root.has("compositeScore")) {
            parsed.result = parseScoringPayload(root, root.optDouble("timestamp", 0.0));
        }
        return parsed;
    }

    private static RehabResult parseScoringPayload(JSONObject payload, double timestamp) {
        RehabResult result = new RehabResult();
        result.totalScore = optDoubleAny(payload, "total_score", "compositeScore", "session_score");
        result.recordId = optStringAny(payload, "record_id", "recordId");
        result.recordType = optStringAny(payload, "record_type", "recordType");
        result.recordIndex = payload.optInt("record_index", payload.optInt("index", 0));
        result.completion = payload.optInt("completion", 0);
        result.level = normalizeLevel(payload.opt("level"));
        result.levelName = optStringAny(payload, "level_name", "levelName");
        result.source = payload.optString("source", "");
        result.advice = optStringAny(payload, "advice", "summary_text");
        result.summaryText = payload.optString("summary_text", "");
        result.statusText = payload.optString("note", "");
        result.timestampText = optStringAny(payload, "csv_time", "timestamp_text");
        if (result.timestampText.isEmpty()) {
            result.timestampText = timestampText(timestamp);
        }

        JSONObject dims = payload.optJSONObject("dimension_scores");
        if (dims == null) {
            dims = payload.optJSONObject("dims");
        }
        readDimensionScores(dims, result);

        readStringArray(payload.optJSONArray("action_names"), result.actionNames);
        readDoubleArray(payload.optJSONArray("action_scores"), result.actionScores);

        if (result.advice == null || result.advice.trim().isEmpty()) {
            result.advice = RehabResult.autoAdvice(result.totalScore);
        }
        if (result.recordType == null || result.recordType.trim().isEmpty()) {
            result.recordType = result.isTrainingRecord() ? "training" : "assessment";
        }
        return result;
    }

    private static RehabResult parseQtStoredResult(JSONObject stored) {
        RehabResult result = new RehabResult();
        result.recordId = optStringAny(stored, "record_id", "recordId");
        result.recordType = optStringAny(stored, "record_type", "recordType");
        result.recordIndex = stored.optInt("record_index", stored.optInt("index", 0));
        result.totalScore = stored.optDouble("compositeScore", 0.0);
        result.level = normalizeLevel(stored.opt("level"));
        result.levelName = stored.optString("levelName", "");
        result.source = optStringAny(stored, "source");
        if (result.source.isEmpty()) {
            result.source = "assessment";
        }
        result.advice = stored.optString("advice", "");
        result.timestampText = stored.optString("timestamp", "");
        JSONObject dims = stored.optJSONObject("dims");
        if (dims == null) {
            dims = stored.optJSONObject("dimension_scores");
        }
        readDimensionScores(dims, result);
        if (result.advice == null || result.advice.trim().isEmpty()) {
            result.advice = RehabResult.autoAdvice(result.totalScore);
        }
        if (result.recordType == null || result.recordType.trim().isEmpty()) {
            result.recordType = result.isTrainingRecord() ? "training" : "assessment";
        }
        return result;
    }

    private static void readRecordArray(JSONArray array, String recordType, List<RehabResult> out) {
        if (array == null) {
            return;
        }
        for (int i = 0; i < array.length(); i++) {
            JSONObject object = array.optJSONObject(i);
            if (object == null) {
                continue;
            }
            RehabResult result = "training".equals(recordType)
                    ? parseTrainingRecord(object)
                    : parseAssessmentRecord(object);
            if (result.hasScore() || !result.advice.trim().isEmpty()) {
                out.add(result);
            }
        }
    }

    private static RehabResult parseTrainingRecord(JSONObject object) {
        RehabResult result = RehabResult.fromJson(object);
        result.recordType = "training";
        if (result.source == null || result.source.trim().isEmpty()) {
            result.source = "training";
        }
        if (result.recordIndex <= 0) {
            result.recordIndex = object.optInt("index", 0);
        }
        if (result.totalScore <= 0.0) {
            result.totalScore = object.optDouble("compositeScore", 0.0);
        }
        if (result.completion <= 0) {
            result.completion = object.optInt("completion", (int) Math.round(result.totalScore));
        }
        if (result.levelName == null || result.levelName.trim().isEmpty()) {
            result.levelName = optStringAny(object, "levelName", "level");
        }
        if ((result.level == null || result.level.trim().isEmpty()) && result.totalScore > 0.0) {
            result.level = scoreLevel(result.totalScore);
        }
        String actionName = optStringAny(object, "actionName", "action_name");
        if (!actionName.isEmpty() && result.actionNames.isEmpty()) {
            result.actionNames.add(actionName);
        }
        if (result.advice == null || result.advice.trim().isEmpty()) {
            result.advice = RehabResult.autoAdvice(result.totalScore);
        }
        if (result.timestampText == null || result.timestampText.trim().isEmpty()) {
            result.timestampText = timestampText(object.optDouble("timestamp", 0.0));
        }
        if (result.recordId == null || result.recordId.trim().isEmpty()) {
            result.recordId = "training:" + result.recordIndex + ":" + result.timestampText;
        }
        return result;
    }

    private static RehabResult parseAssessmentRecord(JSONObject object) {
        JSONObject resultObject = object.optJSONObject("result");
        RehabResult result;
        if (resultObject != null) {
            result = parseQtStoredResult(resultObject);
        } else if (object.has("total_score") || object.has("dimension_scores")) {
            result = parseScoringPayload(object, object.optDouble("timestamp", 0.0));
        } else {
            result = parseQtStoredResult(object);
        }
        result.recordType = "assessment";
        result.source = result.source == null || result.source.trim().isEmpty() ? "assessment" : result.source;
        result.recordIndex = object.optInt("index", result.recordIndex);
        if (result.timestampText == null || result.timestampText.trim().isEmpty()) {
            result.timestampText = optStringAny(object, "timestamp", "timestamp_text");
        }
        if (result.recordId == null || result.recordId.trim().isEmpty()) {
            result.recordId = "assessment:" + result.recordIndex + ":" + result.timestampText;
        }
        return result;
    }

    private static void readDimensionScores(JSONObject dims, RehabResult result) {
        if (dims == null) {
            return;
        }
        Iterator<String> keys = dims.keys();
        while (keys.hasNext()) {
            String key = keys.next();
            double value = dims.optDouble(key, 0.0);
            if ("fatigue".equals(key) && !result.dimensionScores.containsKey("endurance")) {
                result.dimensionScores.put("endurance", value);
            } else {
                result.dimensionScores.put(key, value);
            }
        }
    }

    private static void readStringArray(JSONArray array, java.util.List<String> out) {
        if (array == null) {
            return;
        }
        for (int i = 0; i < array.length(); i++) {
            String value = array.optString(i, "");
            if (!value.trim().isEmpty()) {
                out.add(value);
            }
        }
    }

    private static void readDoubleArray(JSONArray array, java.util.List<Double> out) {
        if (array == null) {
            return;
        }
        for (int i = 0; i < array.length(); i++) {
            out.add(array.optDouble(i, 0.0));
        }
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

    private static String normalizeLevel(Object raw) {
        if (raw == null || raw == JSONObject.NULL) {
            return "";
        }
        String value = String.valueOf(raw).trim().toUpperCase(Locale.US);
        if (value.endsWith(".0")) {
            value = value.substring(0, value.length() - 2);
        }
        if (value.length() == 1 && Character.isDigit(value.charAt(0))) {
            return "L" + value;
        }
        return value;
    }

    private static String timestampText(double timestamp) {
        if (timestamp <= 0.0) {
            return "";
        }
        long millis = timestamp > 100000000000.0 ? (long) timestamp : (long) (timestamp * 1000.0);
        return new SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.CHINA).format(new Date(millis));
    }

    private static String scoreLevel(double score) {
        if (score < 40.0) {
            return "L1";
        }
        if (score <= 60.0) {
            return "L2";
        }
        if (score <= 80.0) {
            return "L3";
        }
        return "L4";
    }
}
