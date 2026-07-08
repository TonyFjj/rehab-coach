#ifndef TRAININGPAGE_H
#define TRAININGPAGE_H

#include <QFrame>
#include <QLabel>
#include <QList>
#include <QProgressBar>
#include <QPushButton>
#include <QScrollArea>
#include <QStringList>
#include <QTimer>
#include <QJsonObject>
#include <QWidget>
#include <QResizeEvent>
#include <QShowEvent>
#include "widgets/actioncard.h"
#include "models/scoreengine.h"
#include "ipc/fusionbridge.h"

#include <QMap>

class EngineBridge;
class VisionPreviewWidget;

class TrainingPage : public QWidget
{
    Q_OBJECT
public:
    explicit TrainingPage(QWidget *parent = nullptr);
    void refresh();
    void applyFontScale();
    void setEngineBridge(EngineBridge *engine);
    void onScoreReady(const ScoreResult &result);
    void onFusionFrame(const FusionFrame &frame);
    void onGuidanceReady(const QString &text);

public slots:
    void startIntegratedTraining();

signals:
    void trainingCompleted(const QString &actionName, const ScoreResult &result, int completion);

private slots:
    void onActionClicked(int actionId);
    void onStartTraining();
    void onStopTraining();
    void onSequenceTick();
    void onEngineConnectionChanged(bool connected);
    void onEngineActionStatus(const QJsonObject &payload);
    void onEngineTrainingProgress(const QJsonObject &payload);
    void onEngineTrainingState(const QJsonObject &payload);
    void onEngineScoring(const QJsonObject &payload);
    void onEngineTrainingPlan(const QJsonObject &payload);
    void onEngineSessionSummary(const QString &text);
    void onEngineCorrection(const QJsonObject &payload);
    void onEngineEncouragement(const QString &text);
    void onEngineVisionPreview(const QJsonObject &payload);
    void onPauseTraining();
    void onResumeTraining();

private:
    struct LevelPlan {
        QString title;
        QString subTitle;
        QString color;
        QStringList actionIds;
        QStringList actionNames;
        QStringList targets;
        QStringList descriptions;
        int baseScore = 70;
        bool fromBackend = false;
        QString bodyRegion;
        QString blockLabel;
        QString setupHint;
        bool suggestIntegration = false;
        bool hasIntegration = false;
    };

    void setupUI();
    void showActionDetail(int actionId);
    void updateLevelTabs();
    LevelPlan levelPlan(int level) const;
    void applyTrainingPlan(const QJsonObject &payload);
    void requestTrainingPlan();
    void rebuildIntegratedPlan();
    void syncPlanFromLevel();
    void updateStepStates();
    void completeTrainingWithScore();
    void finishIntegratedTraining(bool saveResult);
    void sendTrainingEngineCommand(const QString &command);
    int stepIndexForActionId(const QString &actionId) const;
    QString currentLevelCode() const;
    int levelFromCode(const QString &code) const;

    void updateVisionMetricsFromPreview(const QJsonObject &payload);
    void updateVisionPreviewHeight();
    void refreshTrainingHud();
    void applyLevelTabStyles();
    void applyRegionTabStyles();
    void updateRegionTabs();
    void updateBlockGuidance();
    void updateTrainingOverlay(
        const QString &actionName,
        int rep,
        int target,
        double angle,
        const QString &metricName = QString(),
        const QString &metricUnit = QStringLiteral("°"));
    void updateTrainingGifForAction(const QString &actionName);
    void updateTrainingGifForCurrentStep();
    QString trainingGifPathForAction(const QString &actionName) const;
    bool integrationAvailableForLevel(int level) const;
    QString currentBodyRegionCode() const;

protected:
    void resizeEvent(QResizeEvent *event) override;
    void showEvent(QShowEvent *event) override;

    EngineBridge *m_engine = nullptr;
    VisionPreviewWidget *m_visionPreview = nullptr;
    QLabel *m_engineStatus = nullptr;
    QString m_levelColors[4];
    QPushButton *m_levelBtns[4] = {nullptr, nullptr, nullptr, nullptr};
    QPushButton *m_regionBtns[3] = {nullptr, nullptr, nullptr};
    QString m_currentBodyRegion = QStringLiteral("upper");
    bool m_hasIntegrationBlock = false;
    bool m_suggestIntegration = false;
    QString m_setupHint;
    QScrollArea *m_pageScroll = nullptr;
    QWidget *m_pageContent = nullptr;
    QWidget *m_actionContainer = nullptr;
    QList<ActionCard*> m_cards;
    QList<QFrame*> m_stepFrames;
    QList<QLabel*> m_stepBadges;
    QList<QLabel*> m_stepTexts;
    int m_currentLevel = 2;
    int m_selectedAction = -1;

    QWidget *m_trainingPanel = nullptr;
    QLabel *m_actionName = nullptr;
    QProgressBar *m_actionProgress = nullptr;
    QLabel *m_jointAngle = nullptr;
    QLabel *m_guidanceText = nullptr;
    QPushButton *m_startBtn = nullptr;
    QPushButton *m_pauseBtn = nullptr;
    QPushButton *m_resumeBtn = nullptr;
    QPushButton *m_stopBtn = nullptr;
    bool m_training = false;
    bool m_paused = false;
    bool m_engineMode = false;

    QTimer *m_sequenceTimer = nullptr;
    int m_sequenceElapsed = 0;
    int m_currentStep = 0;
    int m_stepSeconds = 8;
    int m_totalSteps = 4;
    int m_backendTotalActions = 0;
    bool m_pendingSave = false;
    QMap<int, LevelPlan> m_backendPlans;

    ScoreResult m_score;
};

#endif // TRAININGPAGE_H
