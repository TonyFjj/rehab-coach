#include "datastorage.h"

#include <QDateTime>
#include <QDir>
#include <QFile>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonParseError>
#include <QStandardPaths>
#include <QtGlobal>

QString DataStorage::storageDir()
{
    QString dir = QStandardPaths::writableLocation(QStandardPaths::AppDataLocation);
    if (dir.isEmpty()) {
        dir = QDir::homePath() + QStringLiteral("/.rehab_coach");
    }
    QDir().mkpath(dir);
    return dir;
}

QString DataStorage::dataFilePath(const QString &fileName)
{
    return QDir(storageDir()).filePath(fileName);
}

bool DataStorage::readJsonFile(const QString &fileName, QJsonObject *root)
{
    if (!root) {
        return false;
    }

    QFile file(dataFilePath(fileName));
    if (!file.exists() || !file.open(QIODevice::ReadOnly | QIODevice::Text)) {
        return false;
    }

    const QByteArray data = file.readAll();
    file.close();

    QJsonParseError error;
    const QJsonDocument doc = QJsonDocument::fromJson(data, &error);
    if (error.error != QJsonParseError::NoError || !doc.isObject()) {
        return false;
    }

    *root = doc.object();
    return true;
}

bool DataStorage::writeJsonFile(const QString &fileName, const QJsonObject &root)
{
    QDir().mkpath(storageDir());
    QFile file(dataFilePath(fileName));
    if (!file.open(QIODevice::WriteOnly | QIODevice::Text | QIODevice::Truncate)) {
        return false;
    }

    const QJsonDocument doc(root);
    file.write(doc.toJson(QJsonDocument::Indented));
    file.close();
    return true;
}

QJsonObject DataStorage::scoreResultToJson(const ScoreResult &result)
{
    QJsonObject obj;
    obj.insert(QStringLiteral("compositeScore"), result.compositeScore);
    obj.insert(QStringLiteral("level"), result.level);
    obj.insert(QStringLiteral("levelName"), result.levelName);
    obj.insert(QStringLiteral("levelColor"), result.levelColor);
    obj.insert(QStringLiteral("advice"), result.advice);
    obj.insert(QStringLiteral("source"), result.source);
    obj.insert(QStringLiteral("timestamp"), result.timestamp.toString(Qt::ISODateWithMs));

    QJsonObject dims;
    for (auto it = result.dims.constBegin(); it != result.dims.constEnd(); ++it) {
        dims.insert(it.key(), it.value());
    }
    obj.insert(QStringLiteral("dims"), dims);

    QJsonArray blockNameArr;
    for (const QString &name : result.blockNames) {
        blockNameArr.append(name);
    }
    obj.insert(QStringLiteral("blockNames"), blockNameArr);

    QJsonArray blockScoreArr;
    for (int score : result.blockScores) {
        blockScoreArr.append(qBound(0, score, 100));
    }
    obj.insert(QStringLiteral("blockScores"), blockScoreArr);
    return obj;
}

ScoreResult DataStorage::scoreResultFromJson(const QJsonObject &obj)
{
    ScoreResult result;
    result.compositeScore = qBound(0, obj.value(QStringLiteral("compositeScore")).toInt(0), 100);
    result.level = obj.value(QStringLiteral("level")).toInt(ScoreEngine::scoreToLevel(result.compositeScore));
    result.levelName = obj.value(QStringLiteral("levelName")).toString(ScoreEngine::levelName(result.level));
    result.levelColor = obj.value(QStringLiteral("levelColor")).toString(ScoreEngine::levelColor(result.level));
    result.advice = obj.value(QStringLiteral("advice")).toString();
    result.source = obj.value(QStringLiteral("source")).toString();
    result.timestamp = QDateTime::fromString(obj.value(QStringLiteral("timestamp")).toString(), Qt::ISODateWithMs);

    const QJsonObject dims = obj.value(QStringLiteral("dims")).toObject();
    for (auto it = dims.constBegin(); it != dims.constEnd(); ++it) {
        result.dims.insert(it.key(), it.value().toDouble(0.0));
    }

    const QJsonArray blockNameArr = obj.value(QStringLiteral("blockNames")).toArray();
    for (const QJsonValue &value : blockNameArr) {
        const QString name = value.toString().trimmed();
        if (!name.isEmpty()) {
            result.blockNames.append(name);
        }
    }

    const QJsonArray blockScoreArr = obj.value(QStringLiteral("blockScores")).toArray();
    for (const QJsonValue &value : blockScoreArr) {
        result.blockScores.append(qBound(0, value.toInt(0), 100));
    }
    return result;
}

bool DataStorage::saveLatestAssessment(const ScoreResult &result)
{
    QJsonObject root;
    root.insert(QStringLiteral("version"), 1);
    root.insert(QStringLiteral("latestAssessment"), scoreResultToJson(result));
    return writeJsonFile(QStringLiteral("latest_assessment.json"), root);
}

bool DataStorage::loadLatestAssessment(ScoreResult *result)
{
    if (!result) {
        return false;
    }

    QJsonObject root;
    if (!readJsonFile(QStringLiteral("latest_assessment.json"), &root)) {
        return false;
    }

    const QJsonObject obj = root.value(QStringLiteral("latestAssessment")).toObject();
    if (obj.isEmpty()) {
        return false;
    }

    *result = scoreResultFromJson(obj);
    return result->timestamp.isValid() || result->compositeScore > 0;
}

bool DataStorage::loadAppSettings(QJsonObject *root)
{
    if (!root) {
        return false;
    }
    if (!readJsonFile(QStringLiteral("app_settings.json"), root)) {
        return false;
    }
    return !root->isEmpty();
}

bool DataStorage::saveAppSettings(const QJsonObject &root)
{
    return writeJsonFile(QStringLiteral("app_settings.json"), root);
}
