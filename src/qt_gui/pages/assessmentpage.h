#ifndef ASSESSMENTPAGE_H
#define ASSESSMENTPAGE_H

#include <QWidget>
#include <QLabel>
#include <QPushButton>
#include <QProgressBar>
#include <QTimer>
#include <QJsonObject>
#include <QResizeEvent>
#include <QStackedWidget>
#include <QScrollArea>
#include <QFrame>

#include "widgets/radarchart.h"
#include "models/scoreengine.h"

class EngineBridge;
class VisionPreviewWidget;

class AssessmentPage : public QWidget
{
    Q_OBJECT
public:
    explicit AssessmentPage(QWidget *parent = nullptr);
    void refresh();
    void setEngineBridge(EngineBridge *engine);
    void applyFontScale();

signals:
    void assessmentCompleted(const ScoreResult &result);

private:
    void applyAssessmentResult(const ScoreResult &result, bool emitCompletion);

private slots:
    void onStartAssessment();
    void onEnterSession();
    void onTick();
    void onScoreReady(const ScoreResult &result);
    void onEngineScoring(const QJsonObject &payload);
    void onEngineConnectionChanged(bool connected);
    void onEngineAssessmentPlan(const QJsonObject &payload);
    void onEngineAssessmentPhase(const QJsonObject &payload);
    void onEngineVisionPreview(const QJsonObject &payload);

private:
    void setupUI();
    void applyFontStyles(const QString &scoreColor = QString());
    void loadStoredAssessment();
    void showResultOnPage(const ScoreResult &result, bool finishedState);
    void resetReadyState();
    void applyAssessmentPhase(const QJsonObject &payload);
    void updateVisionMetricsFromPayload(const QJsonObject &payload);
    QString buildVisionFusionNote(const QJsonObject &payload) const;
    void requestAssessmentPlan();
    QString formatCountdown(int seconds) const;
    void showActionPlan(const QJsonObject &payload);
    void updateVisionPreviewHeight();
    void refreshSessionSubtitleLayout();
    void refreshSessionChrome(const QString &phase);
    void showIntroPage();
    void showSessionPage();
    void beginAssessmentSession();

protected:
    void resizeEvent(QResizeEvent *event) override;

    EngineBridge *m_engine = nullptr;
    bool m_engineMode = false;

    QStackedWidget *m_pageStack = nullptr;
    QWidget *m_introPage = nullptr;
    QWidget *m_sessionPage = nullptr;
    QWidget *m_resultPanel = nullptr;

    QLabel *m_title;
    QLabel *m_voiceHint;
    QProgressBar *m_progress;
    QLabel *m_countdown;
    QLabel *m_actionLabel;
    QLabel *m_subtitle;
    QLabel *m_actionList;
    QLabel *m_instruction;
    QPushButton *m_startBtn;
    QPushButton *m_enterBtn = nullptr;

    VisionPreviewWidget *m_visionPreview = nullptr;
    QScrollArea *m_sessionLowerScroll = nullptr;
    QWidget *m_sessionLowerBody = nullptr;
    QLabel *m_sessionVoiceHint = nullptr;
    QProgressBar *m_sessionProgress = nullptr;
    QLabel *m_sessionCountdown = nullptr;
    QLabel *m_sessionActionLabel = nullptr;
    QLabel *m_sessionSubtitle = nullptr;
    QScrollArea *m_sessionSubtitleScroll = nullptr;

    RadarChart *m_radar;
    QLabel *m_scoreLabel;
    QLabel *m_levelLabel;
    QLabel *m_adviceLabel;

    QTimer *m_timer;
    int m_sessionElapsed = 0;
    int m_totalSeconds = 60;
    int m_collectSeconds = 30;
    int m_phaseDuration = 0;
    int m_phaseElapsed = 0;
    bool m_collectActive = false;
    QString m_lastPhase;
    int m_currentActionIndex = 0;
    int m_totalActions = 4;
    ScoreResult m_result;
    bool m_hasStoredResult = false;
    QString m_visionFusionNote;
};
#endif // ASSESSMENTPAGE_H
