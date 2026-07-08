#ifndef DATASTORAGE_H
#define DATASTORAGE_H

#include <QJsonObject>
#include <QString>
#include "scoreengine.h"

class DataStorage
{
public:
    static QString storageDir();
    static QString dataFilePath(const QString &fileName);

    static bool readJsonFile(const QString &fileName, QJsonObject *root);
    static bool writeJsonFile(const QString &fileName, const QJsonObject &root);

    static QJsonObject scoreResultToJson(const ScoreResult &result);
    static ScoreResult scoreResultFromJson(const QJsonObject &obj);

    static bool saveLatestAssessment(const ScoreResult &result);
    static bool loadLatestAssessment(ScoreResult *result);

    static bool loadAppSettings(QJsonObject *root);
    static bool saveAppSettings(const QJsonObject &root);
};

#endif // DATASTORAGE_H
