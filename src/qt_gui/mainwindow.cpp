#include "mainwindow.h"
#include "models/datastorage.h"
#include "utils/fontscale.h"
#include <QVBoxLayout>
#include <QGuiApplication>
#include <QScreen>
#include <QRect>
#include <QApplication>
#include <QtGlobal>
#include <QTimer>

MainWindow::MainWindow(int themeIndex, QWidget *parent)
    : QMainWindow(parent)
    , m_themeIndex(qBound(1, themeIndex, 4))
    , m_central(nullptr)
    , m_stack(nullptr)
    , m_naviBar(nullptr)
{
    setWindowTitle("康复动作指导教练");
    setObjectName("rehabMainWindow");

    QScreen *screen = QGuiApplication::primaryScreen();
    const QRect available = screen ? screen->availableGeometry() : QRect(0, 0, 1280, 720);
    const int minW = qMin(760, qMax(520, available.width() - 60));
    const int minH = qMin(480, qMax(420, available.height() - 90));
    setMinimumSize(minW, minH);

    const int targetW = qMin(1100, qMax(minW, int(available.width() * 0.86)));
    const int targetH = qMin(680,  qMax(minH, int(available.height() * 0.82)));
    resize(qMin(targetW, available.width()), qMin(targetH, available.height()));
    move(available.center() - rect().center());

    if (available.width() < 1000 || available.height() < 640) {
        setWindowState(windowState() | Qt::WindowMaximized);
    } else if (available.width() <= 1280 && available.height() <= 800) {
        // 10 寸屏常见分辨率：尽量全屏，避免窗口留白导致预览区偏小
        setWindowState(windowState() | Qt::WindowMaximized);
    }

    // 初始化数据模型
    m_scoreEngine = new ScoreEngine(this);
    m_actionDB    = new ActionDB(this);

    // 初始化IPC桥接（传感器数据由其他进程提供）
    m_imuBridge    = new ImuBridge(this);
    m_visionBridge = new VisionBridge(this);
    m_llmBridge    = new LlmBridge(this);
    m_fusionBridge = new FusionBridge(this);
    m_engineBridge = new EngineBridge(this);

    setupUI();
    connectSignals();
    applyTheme(m_themeIndex);
    connect(FontScale::instance(), &FontScale::changed,
            this, &MainWindow::applyFontScale);
    connect(m_settingsPage, &SettingsPage::accessibilityChanged,
            this, &MainWindow::applyFontScale);
    refreshHomeSummary();

    // 默认显示首页
    switchPage(0);
}

MainWindow::~MainWindow() {}

void MainWindow::setupUI()
{
    m_central = new QWidget(this);
    m_central->setObjectName("rehabCentral");
    m_central->setAttribute(Qt::WA_StyledBackground, true);

    QVBoxLayout *mainLayout = new QVBoxLayout(m_central);
    mainLayout->setContentsMargins(10, 8, 10, 8);
    mainLayout->setSpacing(8);

    // 页面堆栈
    m_stack = new QStackedWidget(m_central);
    m_stack->setObjectName("contentStack");
    m_stack->setAttribute(Qt::WA_StyledBackground, true);

    m_homePage     = new HomePage(this);
    m_assessPage   = new AssessmentPage(this);
    m_trainPage    = new TrainingPage(this);
    m_recordsPage  = new RecordsPage(this);
    m_medicalAdvicePage = new MedicalAdvicePage(this);
    m_settingsPage = new SettingsPage(this);

    m_trainPage->setEngineBridge(m_engineBridge);
    m_assessPage->setEngineBridge(m_engineBridge);
    m_settingsPage->setEngineBridge(m_engineBridge);

    m_homePage->setObjectName("rehabPage");
    m_assessPage->setObjectName("rehabPage");
    m_trainPage->setObjectName("rehabPage");
    m_recordsPage->setObjectName("rehabPage");
    m_medicalAdvicePage->setObjectName("rehabPage");
    m_settingsPage->setObjectName("rehabPage");

    m_stack->addWidget(m_homePage);
    m_stack->addWidget(m_assessPage);
    m_stack->addWidget(m_trainPage);
    m_stack->addWidget(m_recordsPage);
    m_stack->addWidget(m_medicalAdvicePage);
    m_stack->addWidget(m_settingsPage);

    // 底部导航栏
    m_naviBar = new NaviBar(m_central);
    m_naviBar->setObjectName("bottomNaviBar");
    m_naviBar->setAttribute(Qt::WA_StyledBackground, true);

    mainLayout->addWidget(m_stack, 1);
    mainLayout->addWidget(m_naviBar, 0);

    setCentralWidget(m_central);
}

void MainWindow::connectSignals()
{
    connect(m_naviBar, &NaviBar::pageSwitched, this, &MainWindow::switchPage);
    connect(m_homePage, &HomePage::startTrainingRequested, this, [this]() {
        switchPage(2);
    });

    // 评分由后端 EngineBridge 推送；本地 IMU 模拟不参与计分
    // connect(m_imuBridge, &ImuBridge::imuDataReady, m_scoreEngine, &ScoreEngine::onImuData);

    // 融合数据 → 训练页面
    connect(m_fusionBridge, &FusionBridge::fusionFrameReady, m_trainPage, &TrainingPage::onFusionFrame);

    // 评分完成 → 首页/训练页
    connect(m_scoreEngine, &ScoreEngine::scoreReady, m_homePage, &HomePage::onScoreUpdated);
    connect(m_scoreEngine, &ScoreEngine::scoreReady, m_trainPage, &TrainingPage::onScoreReady);

    // 测评完成 → 仅同步首页与医疗建议；评估数据不再写入“训练记录”。
    connect(m_assessPage, &AssessmentPage::assessmentCompleted, this, [this](const ScoreResult &result) {
        ScoreResult assessmentResult = result;
        if (assessmentResult.source.isEmpty()) {
            assessmentResult.source = QStringLiteral("assessment");
        }
        if (m_homePage) {
            m_homePage->onScoreUpdated(assessmentResult);
        }
        if (m_trainPage) {
            m_trainPage->onScoreReady(assessmentResult);
        }
        if (m_medicalAdvicePage) {
            m_medicalAdvicePage->setLatestAssessment(assessmentResult);
        }
    });

    // 训练停止并产生有效评分后 → 写入“训练记录”。
    connect(m_trainPage, &TrainingPage::trainingCompleted, this,
            [this](const QString &actionName, const ScoreResult &result, int completion) {
        if (m_recordsPage) {
            ScoreResult trainingResult = result;
            if (trainingResult.source.isEmpty()) {
                trainingResult.source = QStringLiteral("training");
            }
            m_recordsPage->appendTrainingRecord(actionName, trainingResult, completion);
        }
    });

    // LLM指导语 → 训练页
    connect(m_llmBridge, &LlmBridge::guidanceReady, m_trainPage, &TrainingPage::onGuidanceReady);

    // 后端评估评分 → 各页统一同步（评估页、首页、医疗建议）
    connect(m_engineBridge, &EngineBridge::scoringReceived, this,
            [this](const QJsonObject &payload) {
        if (payload.value(QStringLiteral("source")).toString()
                != QStringLiteral("assessment")) {
            return;
        }
        ScoreResult result = ScoreEngine::fromEnginePayload(payload);
        if (result.source.isEmpty()) {
            result.source = QStringLiteral("assessment");
        }
        DataStorage::saveLatestAssessment(result);
        if (m_homePage) {
            m_homePage->onScoreUpdated(result);
        }
        if (m_medicalAdvicePage) {
            m_medicalAdvicePage->setLatestAssessment(result);
        }
    });
}

void MainWindow::refreshHomeSummary()
{
    ScoreResult assessment;
    if (DataStorage::loadLatestAssessment(&assessment) && assessment.compositeScore > 0) {
        if (m_homePage) {
            m_homePage->onScoreUpdated(assessment);
        }
        return;
    }
    if (m_homePage && m_recordsPage && m_recordsPage->lastCompositeScore() > 0) {
        m_homePage->setLastTrainingSummary(m_recordsPage->lastCompositeScore(),
                                           m_recordsPage->lastLevelName(),
                                           m_recordsPage->lastLevelColor(),
                                           m_recordsPage->lastAdvice());
    }
}

QString MainWindow::mainBackgroundPath(int themeIndex) const
{
    return QString(":/res/pic/background-%1.png").arg(qBound(1, themeIndex, 4));
}

QString MainWindow::accentColor(int themeIndex) const
{
    switch (qBound(1, themeIndex, 4)) {
    case 1: return "#fd6c92"; // 粉红
    case 2: return "#ffde49"; // 黄色
    case 3: return "#8293fd"; // 浅紫
    case 4: return "#74fae9"; // 青绿
    default: return "#2E86C1";
    }
}

QString MainWindow::accentLightColor(int themeIndex) const
{
    switch (qBound(1, themeIndex, 4)) {
    case 1: return "#ffe8ef";
    case 2: return "#fff7cf";
    case 3: return "#eef0ff";
    case 4: return "#dcfff9";
    default: return "#E8F4FD";
    }
}

QString MainWindow::accentDarkColor(int themeIndex) const
{
    switch (qBound(1, themeIndex, 4)) {
    case 1: return "#e83737";
    case 2: return "#80712d";
    case 3: return "#4861fb";
    case 4: return "#316f67";
    default: return "#1A5276";
    }
}

void MainWindow::applyTheme(int themeIndex)
{
    m_themeIndex = qBound(1, themeIndex, 4);
    const QString bg = mainBackgroundPath(m_themeIndex);
    const QString accent = accentColor(m_themeIndex);
    const QString accentLight = accentLightColor(m_themeIndex);
    const QString accentDark = accentDarkColor(m_themeIndex);

    const QString centralStyle = QString(R"(
        QWidget#rehabCentral {
            border-image: url(%1) 0 0 0 0 stretch stretch;
        }
        QStackedWidget#contentStack {
            background-color: rgba(255, 255, 255, 214);
            border: 1px solid rgba(255, 255, 255, 190);
            border-radius: 22px;
        }
        QWidget#rehabPage {
            background-color: transparent;
            border: none;
        }
        QLabel {
            background-color: transparent;
        }
        QScrollArea, QScrollArea > QWidget, QScrollArea > QWidget > QWidget {
            background-color: transparent;
            border: none;
        }
        QScrollBar:vertical {
            border: none;
            background: transparent;
            width: 8px;
        }
        QScrollBar::handle:vertical {
            background: %2;
            border-radius: 4px;
            min-height: 30px;
        }
    )").arg(bg, accent);
    m_central->setStyleSheet(centralStyle);

    const QString naviStyle = QString(R"(
        QWidget#bottomNaviBar {
            background-color: rgba(255, 255, 255, 225);
            border: 1px solid rgba(255, 255, 255, 190);
            border-radius: 18px;
        }
        QWidget#bottomNaviBar QPushButton {
            border: none;
            border-radius: 12px;
            background: transparent;
            color: #606060;
            font-size: %3px;
            font-weight: normal;
        }
        QWidget#bottomNaviBar QPushButton:checked {
            background: %1;
            color: %2;
            font-weight: bold;
        }
    )").arg(accentLight, accentDark).arg(FontScale::instance()->px(13));
    m_naviBar->setStyleSheet(naviStyle);
}

void MainWindow::applyFontScale()
{
    FontScale::instance()->applyApplicationFont(qApp);
    applyTheme(m_themeIndex);
    if (m_naviBar) {
        m_naviBar->setMinimumHeight(FontScale::instance()->largeMode() ? 78 : 62);
        m_naviBar->setMaximumHeight(FontScale::instance()->largeMode() ? 96 : 82);
    }
    m_homePage->applyFontScale();
    m_assessPage->applyFontScale();
    m_trainPage->applyFontScale();
    m_recordsPage->applyFontScale();
    m_medicalAdvicePage->applyFontScale();
    m_settingsPage->applyFontScale();
}

void MainWindow::switchPage(int index)
{
    if (index < 0 || index >= m_stack->count()) {
        return;
    }

    m_stack->setCurrentIndex(index);
    m_naviBar->setActiveIndex(index);

    // 刷新页面
    switch (index) {
    case 0:
        refreshHomeSummary();
        m_homePage->refresh();
        break;
    case 1: m_assessPage->refresh();   break;
    case 2: m_trainPage->refresh();    break;
    case 3: m_recordsPage->refresh();  break;
    case 4: m_medicalAdvicePage->refresh(); break;
    case 5: m_settingsPage->refresh(); break;
    default: break;
    }
}
