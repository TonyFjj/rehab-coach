#ifndef HOMEPAGE_H
#define HOMEPAGE_H

#include <QWidget>
#include <QLabel>
#include <QPushButton>
#include <QVBoxLayout>
#include <QPropertyAnimation>
#include "widgets/arcgauge.h"
#include "models/scoreengine.h"

class HomePage : public QWidget
{
    Q_OBJECT
public:
    explicit HomePage(QWidget *parent = nullptr);
    void refresh();
    void onScoreUpdated(const ScoreResult &result);
    void setLastTrainingSummary(int compositeScore, const QString &levelName, const QString &levelColor, const QString &advice = QString());
    void applyFontScale();

signals:
    void startTrainingRequested();

private:
    void setupUI();
    void animateGaugeToLastScore();

    ArcGauge *m_gauge = nullptr;
    QLabel *m_greeting = nullptr;
    QLabel *m_levelLabel = nullptr;
    QLabel *m_adviceLabel = nullptr;
    QLabel *m_todayInfo = nullptr;
    QPushButton *m_btnAssess = nullptr;
    QPushButton *m_btnTrain = nullptr;
    QPushButton *m_btnRecords = nullptr;
    QPushButton *m_btnMedicalAdvice = nullptr;
    QPushButton *m_btnSettings = nullptr;
    QPropertyAnimation *m_gaugeAnimation = nullptr;
    ScoreResult m_lastScore;
};
#endif // HOMEPAGE_H
