#ifndef SCOREENGINE_H
#define SCOREENGINE_H

#include <QObject>
#include <QMap>
#include <QDateTime>
#include <QStringList>
#include <QJsonObject>
#include <QPair>

struct ScoreResult {
    int compositeScore = 0;       // 0-100综合分
    int level = 0;                // 1-4级别
    QString levelName;            // L1/L2/L3/L4
    QString levelColor;           // 级别颜色
    QString advice;               // 康复建议
    QString source;               // assessment / training
    QStringList blockNames;       // 各动作名称（来自后端 yaml）
    QList<int> blockScores;       // 各动作得分 0-100
    QMap<QString, double> dims;   // 维度得分(0-1)
    QDateTime timestamp;
};

class ScoreEngine : public QObject
{
    Q_OBJECT
public:
    explicit ScoreEngine(QObject *parent = nullptr);

    // 根据IMU原始数据计算评分
    ScoreResult calculate(const QMap<QString, double> &rawFeatures);

    // 级别判定
    static int scoreToLevel(int score);
    static QString levelName(int level);
    static QString levelColor(int level);
    static QString randomAdviceForScore(int score);
    static ScoreResult fromEnginePayload(const QJsonObject &payload);

    // 六维得分展示（与 RadarChart 一致：原始分/满分 → 百分比）
    static QString resolveEnglishDimensionKey(const QString &key);
    static QString dimensionCnName(const QString &englishKey);
    static double dimensionMaxPoints(const QString &englishKey);
    static double dimensionRawValue(const ScoreResult &result, const QString &englishKey);
    static double dimensionDisplayRatio(const ScoreResult &result, const QString &englishOrCnKey);
    static int dimensionDisplayPercent(const ScoreResult &result, const QString &englishOrCnKey);
    static QPair<int, int> dimensionDisplayPoints(const ScoreResult &result, const QString &englishOrCnKey);
    static QString dimensionScoreLabel(const ScoreResult &result, const QString &englishOrCnKey);
    static bool assessmentDimensionsEqual(const ScoreResult &a, const ScoreResult &b);

public slots:
    void onImuData(const QMap<QString, double> &rawData);

signals:
    void scoreReady(const ScoreResult &result);

private:
    // 6维权重
    QMap<QString, double> m_weights;
};

#endif // SCOREENGINE_H
