#ifndef MAINWINDOW_H
#define MAINWINDOW_H

#include <QMainWindow>
#include <QStackedWidget>
#include "widgets/navibar.h"
#include "pages/homepage.h"
#include "pages/assessmentpage.h"
#include "pages/trainingpage.h"
#include "pages/recordspage.h"
#include "pages/medicaladvicepage.h"
#include "pages/settingspage.h"
#include "ipc/imubridge.h"
#include "ipc/visionbridge.h"
#include "ipc/llmbridge.h"
#include "ipc/fusionbridge.h"
#include "ipc/enginebridge.h"
#include "models/scoreengine.h"
#include "models/actiondb.h"

class MainWindow : public QMainWindow
{
    Q_OBJECT

public:
    explicit MainWindow(int themeIndex = 1, QWidget *parent = nullptr);
    ~MainWindow();

    // 全局IPC桥接访问
    ImuBridge*      imuBridge()    const { return m_imuBridge; }
    VisionBridge*   visionBridge() const { return m_visionBridge; }
    LlmBridge*      llmBridge()    const { return m_llmBridge; }
    FusionBridge*   fusionBridge() const { return m_fusionBridge; }
    EngineBridge*   engineBridge() const { return m_engineBridge; }
    ScoreEngine*    scoreEngine()  const { return m_scoreEngine; }
    ActionDB*       actionDB()     const { return m_actionDB; }

public slots:
    void switchPage(int index);
    void applyTheme(int themeIndex);
    void applyFontScale();

private:
    void setupUI();
    void connectSignals();
    void refreshHomeSummary();
    QString mainBackgroundPath(int themeIndex) const;
    QString accentColor(int themeIndex) const;
    QString accentLightColor(int themeIndex) const;
    QString accentDarkColor(int themeIndex) const;

    int m_themeIndex;
    QWidget *m_central;
    QStackedWidget *m_stack;
    NaviBar         *m_naviBar;

    HomePage        *m_homePage;
    AssessmentPage  *m_assessPage;
    TrainingPage    *m_trainPage;
    RecordsPage     *m_recordsPage;
    MedicalAdvicePage *m_medicalAdvicePage;
    SettingsPage    *m_settingsPage;

    // IPC桥接
    ImuBridge       *m_imuBridge;
    VisionBridge    *m_visionBridge;
    LlmBridge       *m_llmBridge;
    FusionBridge    *m_fusionBridge;
    EngineBridge    *m_engineBridge;

    // 数据模型
    ScoreEngine     *m_scoreEngine;
    ActionDB        *m_actionDB;
};

#endif // MAINWINDOW_H
