#include "trainingpage.h"
#include "ipc/enginebridge.h"
#include "widgets/visionpreviewwidget.h"
#include "utils/elderux.h"
#include "utils/fontscale.h"

#include <QFrame>
#include <QVBoxLayout>
#include <QHBoxLayout>
#include <QGridLayout>
#include <QJsonArray>
#include <QDateTime>
#include <QGuiApplication>
#include <QCoreApplication>
#include <QDir>
#include <QFile>
#include <QLoggingCategory>
#include <QScreen>

TrainingPage::TrainingPage(QWidget *parent) : QWidget(parent)
{
    m_sequenceTimer = new QTimer(this);
    m_sequenceTimer->setInterval(1000);
    connect(m_sequenceTimer, &QTimer::timeout, this, &TrainingPage::onSequenceTick);
    setupUI();
}

void TrainingPage::setEngineBridge(EngineBridge *engine)
{
    if (m_engine == engine) {
        return;
    }
    if (m_engine) {
        disconnect(m_engine, nullptr, this, nullptr);
    }
    m_engine = engine;
    if (!m_engine) {
        return;
    }

    connect(m_engine, &EngineBridge::connectionChanged,
            this, &TrainingPage::onEngineConnectionChanged);
    connect(m_engine, &EngineBridge::actionStatusReceived,
            this, &TrainingPage::onEngineActionStatus);
    connect(m_engine, &EngineBridge::trainingProgressReceived,
            this, &TrainingPage::onEngineTrainingProgress);
    connect(m_engine, &EngineBridge::trainingStateReceived,
            this, &TrainingPage::onEngineTrainingState);
    connect(m_engine, &EngineBridge::scoringReceived,
            this, &TrainingPage::onEngineScoring);
    connect(m_engine, &EngineBridge::trainingPlanReceived,
            this, &TrainingPage::onEngineTrainingPlan);
    connect(m_engine, &EngineBridge::sessionSummaryReceived,
            this, &TrainingPage::onEngineSessionSummary);
    connect(m_engine, &EngineBridge::correctionReceived,
            this, &TrainingPage::onEngineCorrection);
    connect(m_engine, &EngineBridge::encouragementReceived,
            this, &TrainingPage::onEngineEncouragement);
    connect(m_engine, &EngineBridge::visionPreviewReceived,
            this, &TrainingPage::onEngineVisionPreview);

    onEngineConnectionChanged(m_engine->isConnected());
}

void TrainingPage::setupUI()
{
    QVBoxLayout *outer = new QVBoxLayout(this);
    outer->setContentsMargins(0, 0, 0, 0);
    outer->setSpacing(0);

    m_engineStatus = new QLabel(this);
    m_engineStatus->hide();

    m_pageScroll = new QScrollArea(this);
    m_pageScroll->setWidgetResizable(true);
    m_pageScroll->setFrameShape(QFrame::NoFrame);
    m_pageScroll->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    m_pageScroll->setStyleSheet(
        QStringLiteral("QScrollArea{background:transparent; border:none;}"));

    m_pageContent = new QWidget();
    m_pageContent->setStyleSheet(QStringLiteral("background:transparent;"));
    QVBoxLayout *lay = new QVBoxLayout(m_pageContent);
    lay->setContentsMargins(12, 8, 12, 8);
    lay->setSpacing(6);

    m_visionPreview = new VisionPreviewWidget(m_pageContent);
    m_visionPreview->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
    lay->addWidget(m_visionPreview);

    QWidget *controlPanel = new QWidget(m_pageContent);
    controlPanel->setStyleSheet(QStringLiteral("background:transparent;"));
    QVBoxLayout *controlLay = new QVBoxLayout(controlPanel);
    controlLay->setContentsMargins(0, 0, 0, 0);
    controlLay->setSpacing(4);

    QWidget *levelBar = new QWidget(controlPanel);
    levelBar->setStyleSheet(
        "background-color: rgba(0, 0, 0, 75); border-radius:10px;");
    QHBoxLayout *tabLay = new QHBoxLayout(levelBar);
    tabLay->setContentsMargins(6, 4, 6, 4);
    tabLay->setSpacing(6);
    QStringList levels;
    levels << QStringLiteral("L1 卧床主动") << QStringLiteral("L2 坐姿辅助")
           << QStringLiteral("L3 站立主动") << QStringLiteral("L4 全幅主动");
    m_levelColors[0] = QStringLiteral("#E74C3C");
    m_levelColors[1] = QStringLiteral("#F39C12");
    m_levelColors[2] = QStringLiteral("#2E86C1");
    m_levelColors[3] = QStringLiteral("#27AE60");
    for (int i = 0; i < 4; ++i) {
        m_levelBtns[i] = new QPushButton(levels[i], levelBar);
        m_levelBtns[i]->setCheckable(true);
        m_levelBtns[i]->setChecked(i == 1);
        m_levelBtns[i]->setMinimumHeight(40);
        connect(m_levelBtns[i], &QPushButton::clicked, this, [this, i]() {
            if (m_training) {
                return;
            }
            m_currentLevel = i + 1;
            updateLevelTabs();
            requestTrainingPlan();
        });
        tabLay->addWidget(m_levelBtns[i]);
    }
    controlLay->addWidget(levelBar);

    QWidget *regionBar = new QWidget(controlPanel);
    regionBar->setStyleSheet(
        "background-color: rgba(0, 0, 0, 75); border-radius:10px;");
    QHBoxLayout *regionLay = new QHBoxLayout(regionBar);
    regionLay->setContentsMargins(6, 4, 6, 4);
    regionLay->setSpacing(6);
    const QStringList regionLabels = {
        QStringLiteral("上肢训练"),
        QStringLiteral("下肢训练"),
        QStringLiteral("整合课"),
    };
    const QStringList regionCodes = {
        QStringLiteral("upper"),
        QStringLiteral("lower"),
        QStringLiteral("integration"),
    };
    for (int i = 0; i < 3; ++i) {
        m_regionBtns[i] = new QPushButton(regionLabels.at(i), regionBar);
        m_regionBtns[i]->setCheckable(true);
        m_regionBtns[i]->setChecked(i == 0);
        m_regionBtns[i]->setMinimumHeight(40);
        connect(m_regionBtns[i], &QPushButton::clicked, this, [this, i, regionCodes]() {
            if (m_training) {
                return;
            }
            m_currentBodyRegion = regionCodes.at(i);
            updateRegionTabs();
            requestTrainingPlan();
        });
        regionLay->addWidget(m_regionBtns[i]);
    }
    controlLay->addWidget(regionBar);
    lay->addWidget(controlPanel);

    m_actionContainer = new QWidget(m_pageContent);
    m_actionContainer->setStyleSheet(QStringLiteral("background:transparent;"));
    lay->addWidget(m_actionContainer);

    m_guidanceText = new QLabel(m_pageContent);
    m_guidanceText->setWordWrap(true);
    m_guidanceText->setStyleSheet(
        "font-size:14px; color:#1A5276; background:#F8FBFF; border:1px solid #D0DDE8;"
        "border-radius:10px; padding:8px;");
    m_guidanceText->hide();
    lay->addWidget(m_guidanceText);
    lay->addStretch(1);

    m_pageScroll->setWidget(m_pageContent);
    outer->addWidget(m_pageScroll);

    m_actionProgress = new QProgressBar(m_pageContent);
    m_actionProgress->setRange(0, 100);
    m_actionProgress->setValue(0);
    m_actionProgress->setTextVisible(false);
    m_actionProgress->setFixedHeight(14);
    m_actionProgress->setStyleSheet(
        "QProgressBar{border:1px solid #D0DDE8; border-radius:8px; background:#EDF3F8; padding:1px;}"
        "QProgressBar::chunk{background:#27AE60; border-radius:7px;}");

    m_startBtn = new QPushButton(QStringLiteral("开始训练"), m_pageContent);
    m_startBtn->setMinimumHeight(48);
    m_startBtn->setStyleSheet(
        "QPushButton{background:#27AE60; color:white; border:none; border-radius:12px;"
        "font-size:16px; font-weight:bold; padding:8px 18px;}"
        "QPushButton:pressed{background:#1E8449;}"
        "QPushButton:disabled{background:#A0A0A0;}");

    m_stopBtn = new QPushButton(QStringLiteral("停止训练"), m_pageContent);
    m_stopBtn->setMinimumHeight(48);
    m_stopBtn->setStyleSheet(
        "QPushButton{background:#E74C3C; color:white; border:none; border-radius:12px;"
        "font-size:16px; font-weight:bold; padding:8px 18px;}"
        "QPushButton:pressed{background:#C0392B;}");
    m_stopBtn->hide();

    m_pauseBtn = new QPushButton(QStringLiteral("暂停"), m_pageContent);
    m_pauseBtn->setMinimumHeight(48);
    m_pauseBtn->setStyleSheet(
        "QPushButton{background:#F39C12; color:white; border:none; border-radius:12px;"
        "font-size:16px; font-weight:bold; padding:8px 18px;}"
        "QPushButton:pressed{background:#D68910;}"
        "QPushButton:disabled{background:#A0A0A0;}");
    m_pauseBtn->hide();

    m_resumeBtn = new QPushButton(QStringLiteral("继续"), m_pageContent);
    m_resumeBtn->setMinimumHeight(48);
    m_resumeBtn->setStyleSheet(
        "QPushButton{background:#2E86C1; color:white; border:none; border-radius:12px;"
        "font-size:16px; font-weight:bold; padding:8px 18px;}"
        "QPushButton:pressed{background:#1A5276;}"
        "QPushButton:disabled{background:#A0A0A0;}");
    m_resumeBtn->hide();

    connect(m_startBtn, &QPushButton::clicked, this, &TrainingPage::onStartTraining);
    connect(m_pauseBtn, &QPushButton::clicked, this, &TrainingPage::onPauseTraining);
    connect(m_resumeBtn, &QPushButton::clicked, this, &TrainingPage::onResumeTraining);
    connect(m_stopBtn, &QPushButton::clicked, this, &TrainingPage::onStopTraining);

    applyLevelTabStyles();
    updateRegionTabs();
    rebuildIntegratedPlan();
    refreshTrainingHud();
    if (m_visionPreview) {
        m_visionPreview->setBottomBarText(
            QStringLiteral("📷 检测中 ｜ 训练时检测遮挡、多人与逆光"));
    }
    updateVisionPreviewHeight();
}

void TrainingPage::applyFontScale()
{
    const FontScale *fs = FontScale::instance();
    const int btnH = fs->largeMode() ? 56 : 48;
    if (m_guidanceText) {
        m_guidanceText->setStyleSheet(
            QStringLiteral(
                "font-size:%1px; color:#1A5276; background:#F8FBFF; border:1px solid #D0DDE8;"
                "border-radius:10px; padding:8px;")
                .arg(fs->px(14)));
    }
    auto styleTrainBtn = [fs, btnH](QPushButton *btn, const QString &bg, const QString &pressed) {
        if (!btn) {
            return;
        }
        btn->setMinimumHeight(btnH);
        btn->setStyleSheet(QStringLiteral(
            "QPushButton{background:%1; color:white; border:none; border-radius:12px;"
            "font-size:%2px; font-weight:bold; padding:8px 18px;}"
            "QPushButton:pressed{background:%3;}"
            "QPushButton:disabled{background:#A0A0A0;}")
            .arg(bg, QString::number(fs->px(16)), pressed));
    };
    styleTrainBtn(m_startBtn, QStringLiteral("#27AE60"), QStringLiteral("#1E8449"));
    styleTrainBtn(m_stopBtn, QStringLiteral("#E74C3C"), QStringLiteral("#C0392B"));
    styleTrainBtn(m_pauseBtn, QStringLiteral("#F39C12"), QStringLiteral("#D68910"));
    styleTrainBtn(m_resumeBtn, QStringLiteral("#2E86C1"), QStringLiteral("#1A5276"));

    const int regionH = fs->largeMode() ? 48 : 40;
    for (int i = 0; i < 3; ++i) {
        if (m_regionBtns[i]) {
            m_regionBtns[i]->setMinimumHeight(regionH);
        }
    }
    applyLevelTabStyles();
    applyRegionTabStyles();
    rebuildIntegratedPlan();
    refreshTrainingHud();
}

void TrainingPage::refreshTrainingHud()
{
    if (!m_visionPreview || !m_engineStatus) {
        return;
    }
    const QString engineLine = m_engineStatus->text().isEmpty()
        ? QStringLiteral("引擎：未连接")
        : m_engineStatus->text();
    const LevelPlan plan = levelPlan(m_currentLevel);
    const QString blockLine = plan.blockLabel.isEmpty()
        ? QStringLiteral("上肢训练")
        : plan.blockLabel;
    m_visionPreview->setTopRightText(
        QStringLiteral("康复训练 · %1\n%2").arg(blockLine, engineLine));
}

bool TrainingPage::integrationAvailableForLevel(int level) const
{
    return level == 2 || level == 4;
}

QString TrainingPage::currentBodyRegionCode() const
{
    return m_currentBodyRegion;
}

void TrainingPage::applyRegionTabStyles()
{
    const QString color = QStringLiteral("#1A5276");
    for (int i = 0; i < 3; ++i) {
        if (!m_regionBtns[i]) {
            continue;
        }
        const bool checked = (i == 0 && m_currentBodyRegion == QStringLiteral("upper"))
                             || (i == 1 && m_currentBodyRegion == QStringLiteral("lower"))
                             || (i == 2 && m_currentBodyRegion == QStringLiteral("integration"));
        m_regionBtns[i]->setStyleSheet(
            ElderUx::levelBtnStyle(color, checked));
    }
}

void TrainingPage::updateRegionTabs()
{
    m_hasIntegrationBlock = integrationAvailableForLevel(m_currentLevel);
    for (int i = 0; i < 3; ++i) {
        if (!m_regionBtns[i]) {
            continue;
        }
        const bool isIntegration = (i == 2);
        m_regionBtns[i]->setChecked(
            (i == 0 && m_currentBodyRegion == QStringLiteral("upper"))
            || (i == 1 && m_currentBodyRegion == QStringLiteral("lower"))
            || (i == 2 && m_currentBodyRegion == QStringLiteral("integration")));
        if (isIntegration) {
            const QString label = (m_suggestIntegration && m_hasIntegrationBlock)
                ? QStringLiteral("整合课 推荐")
                : QStringLiteral("整合课");
            m_regionBtns[i]->setText(label);
            m_regionBtns[i]->setEnabled(m_hasIntegrationBlock && !m_training);
        } else {
            m_regionBtns[i]->setEnabled(!m_training);
        }
    }
    if (!m_hasIntegrationBlock && m_currentBodyRegion == QStringLiteral("integration")) {
        m_currentBodyRegion = QStringLiteral("upper");
    }
    applyRegionTabStyles();
}

void TrainingPage::updateBlockGuidance()
{
    if (!m_guidanceText || m_training) {
        return;
    }
    m_guidanceText->hide();
}

void TrainingPage::updateTrainingOverlay(
    const QString &actionName,
    int rep,
    int target,
    double angle,
    const QString &metricName,
    const QString &metricUnit)
{
    if (!m_visionPreview) {
        return;
    }
    if (!m_training) {
        m_visionPreview->setTopLeftText(QString());
        return;
    }

    QStringList lines;
    if (!actionName.isEmpty()) {
        lines << QStringLiteral("动作：%1").arg(actionName);
    }
    if (target > 0 && rep >= 0) {
        lines << QStringLiteral("次数：%1 / %2").arg(rep).arg(target);
    } else if (rep >= 0) {
        lines << QStringLiteral("次数：%1").arg(rep);
    }
    if (angle > 0 || rep >= 0) {
        QString label = QStringLiteral("角度");
        if (metricName == QStringLiteral("leg_raise_angle")) {
            label = QStringLiteral("抬腿");
        } else if (metricName == QStringLiteral("foot_height")
                   || metricName == QStringLiteral("step_distance")) {
            label = QStringLiteral("幅度");
        }
        const QString unit = metricUnit.isEmpty() ? QStringLiteral("°") : metricUnit;
        lines << QStringLiteral("%1：%2%3").arg(label).arg(qRound(angle)).arg(unit);
    }

    if (lines.isEmpty()) {
        m_visionPreview->setTopLeftText(QString());
        return;
    }
    m_visionPreview->setTopLeftText(lines.join(QStringLiteral("\n")));
    updateTrainingGifForAction(actionName);
}

void TrainingPage::updateTrainingGifForAction(const QString &actionName)
{
    if (!m_visionPreview) {
        return;
    }

    const QString gifPath = trainingGifPathForAction(actionName);
    if (gifPath.isEmpty()) {
        qWarning("TrainingPage: no GIF mapping for action '%s'", qPrintable(actionName));
        m_visionPreview->clearRightCameraGif();
        return;
    }
    qInfo("TrainingPage: set GIF for '%s' -> %s", qPrintable(actionName), qPrintable(gifPath));
    m_visionPreview->setRightCameraGif(gifPath);
}

void TrainingPage::updateTrainingGifForCurrentStep()
{
    const LevelPlan plan = levelPlan(m_currentLevel);
    if (m_currentStep >= 0 && m_currentStep < plan.actionNames.size()) {
        updateTrainingGifForAction(plan.actionNames.at(m_currentStep));
    } else if (!plan.actionNames.isEmpty()) {
        updateTrainingGifForAction(plan.actionNames.first());
    }
}

QString TrainingPage::trainingGifPathForAction(const QString &actionName) const
{
    const QString raw = actionName.trimmed();
    if (raw.isEmpty()) {
        return QString();
    }

    const QString compact = QString(raw)
        .remove(QChar(0x3000))
        .remove(QChar(' '))
        .remove(QStringLiteral("训练中"))
        .remove(QStringLiteral("综合训练"))
        .remove(QStringLiteral("动作："))
        .trimmed();

    auto path = [](const QString &fileName) -> QString {
        const QString base = fileName + QStringLiteral(".gif");
        const QString appDir = QCoreApplication::applicationDirPath();
        const QString envDir = qEnvironmentVariable("REHAB_GIF_DIR");
        const QStringList roots = {
            envDir,
            appDir + QStringLiteral("/res/pic/training_gifs/"),
            appDir + QStringLiteral("/../res/pic/training_gifs/"),
            appDir + QStringLiteral("/../../res/pic/training_gifs/"),
        appDir + QStringLiteral("/../../res/pic/training_gifs/"),
        appDir + QStringLiteral("/../../../src/qt_gui/res/pic/training_gifs/"),
    };
    for (const QString &root : roots) {
            if (root.isEmpty()) {
                continue;
            }
            const QString abs = QDir(root).absoluteFilePath(base);
            if (QFile::exists(abs)) {
                return abs;
            }
        }
        const QString srcDir = appDir + QStringLiteral("/../../res/pic/training_gifs/");
        const QString srcAbs = QDir(srcDir).absoluteFilePath(base);
        if (QFile::exists(srcAbs)) {
            return srcAbs;
        }
        return QString();
    };

    static const QMap<QString, QString> aliases = {
        {QStringLiteral("肩前屈"), QStringLiteral("卧床主动肩关节前屈")},
        {QStringLiteral("肩外展"), QStringLiteral("卧床主动肩关节外展")},
        {QStringLiteral("主动屈膝"), QStringLiteral("卧床主动膝关节屈伸")},
        {QStringLiteral("直腿抬高"), QStringLiteral("仰卧直腿交替抬高")},
        {QStringLiteral("前屈上举"), QStringLiteral("坐姿肩关节主动前屈")},
        {QStringLiteral("坐姿肩关节前屈上举"), QStringLiteral("坐姿肩关节主动前屈")},
        {QStringLiteral("坐姿肩关节外展"), QStringLiteral("坐姿肩关节外展举")},
        {QStringLiteral("侧向外展"), QStringLiteral("坐姿肩关节外展举")},
        {QStringLiteral("坐姿膝关节伸展"), QStringLiteral("坐姿膝关节主动伸屈")},
        {QStringLiteral("下肢伸展"), QStringLiteral("坐姿膝关节主动伸屈")},
        {QStringLiteral("上肢协调"), QStringLiteral("坐姿上肢协调性训练")},
        {QStringLiteral("肩部活动"), QStringLiteral("站立肩关节全幅前屈上举")},
        {QStringLiteral("站立肩关节全幅前屈"), QStringLiteral("站立肩关节全幅前屈上举")},
        {QStringLiteral("下肢稳定"), QStringLiteral("站立半蹲训练")},
        {QStringLiteral("重心控制"), QStringLiteral("站立肩关节全幅外展")},
        {QStringLiteral("站立重心转移"), QStringLiteral("站立单脚平衡训练")},
        {QStringLiteral("平衡维持"), QStringLiteral("站立单脚平衡训练")},
        {QStringLiteral("复合协调"), QStringLiteral("太极拳式复合运动")},
        {QStringLiteral("负重控制"), QStringLiteral("站立上肢负重训练")},
        {QStringLiteral("单脚平衡"), QStringLiteral("站立单脚平衡进阶")},
        {QStringLiteral("旋转协调"), QStringLiteral("战力身体旋转协调训练")},
        {QStringLiteral("站立身体旋转协调"), QStringLiteral("战力身体旋转协调训练")},
        {QStringLiteral("站立身体旋转协调训练"), QStringLiteral("战力身体旋转协调训练")},
    };

    if (aliases.contains(compact)) {
        return path(aliases.value(compact));
    }

    const QStringList exactNames = {
        QStringLiteral("仰卧直腿交替抬高"),
        QStringLiteral("卧床主动肩关节前屈"),
        QStringLiteral("卧床主动肩关节外展"),
        QStringLiteral("卧床主动膝关节屈伸"),
        QStringLiteral("坐姿上肢协调性训练"),
        QStringLiteral("坐姿肩关节主动前屈"),
        QStringLiteral("坐姿肩关节外展举"),
        QStringLiteral("坐姿膝关节主动伸屈"),
        QStringLiteral("太极拳式复合运动"),
        QStringLiteral("战力身体旋转协调训练"),
        QStringLiteral("站立上肢负重训练"),
        QStringLiteral("站立半蹲训练"),
        QStringLiteral("站立单脚平衡训练"),
        QStringLiteral("站立单脚平衡进阶"),
        QStringLiteral("站立肩关节全幅前屈上举"),
        QStringLiteral("站立肩关节全幅外展"),
    };
    for (const QString &name : exactNames) {
        if (compact == name || compact.contains(name) || name.contains(compact)) {
            return path(name);
        }
    }

    return QString();
}

void TrainingPage::applyLevelTabStyles()
{
    for (int i = 0; i < 4; ++i) {
        if (!m_levelBtns[i]) {
            continue;
        }
        m_levelBtns[i]->setStyleSheet(
            ElderUx::levelBtnStyle(m_levelColors[i], i + 1 == m_currentLevel));
    }
}

void TrainingPage::updateVisionPreviewHeight()
{
    if (!m_visionPreview) {
        return;
    }
    QScreen *screen = QGuiApplication::primaryScreen();
    const int sh = screen ? screen->availableGeometry().height() : 720;
    const int panelW = m_pageScroll && m_pageScroll->viewport()
                           ? m_pageScroll->viewport()->width()
                           : width();
    const int viewportH = m_pageScroll && m_pageScroll->viewport()
                              ? m_pageScroll->viewport()->height()
                              : sh;
    const int h = ElderUx::trainingVisionPreviewHeight(panelW, viewportH, sh);
    m_visionPreview->setFixedHeight(h);
}

void TrainingPage::resizeEvent(QResizeEvent *event)
{
    QWidget::resizeEvent(event);
    updateVisionPreviewHeight();
}

void TrainingPage::showEvent(QShowEvent *event)
{
    QWidget::showEvent(event);
    updateVisionPreviewHeight();
}

TrainingPage::LevelPlan TrainingPage::levelPlan(int level) const
{
    if (m_backendPlans.contains(level)) {
        return m_backendPlans.value(level);
    }

    const int l = qBound(1, level, 4);
    LevelPlan p;
    switch (l) {
    case 1:
        p.title = QStringLiteral("L1 卧床主动综合训练");
        p.subTitle = QStringLiteral("卧床主动肩关节前屈、卧床主动肩关节外展、卧床主动膝关节屈伸、仰卧直腿交替抬高");
        p.color = QStringLiteral("#E74C3C");
        p.actionNames << QStringLiteral("卧床主动肩关节前屈") << QStringLiteral("卧床主动肩关节外展")
                      << QStringLiteral("卧床主动膝关节屈伸") << QStringLiteral("仰卧直腿交替抬高");
        p.targets << QStringLiteral("自主抬臂") << QStringLiteral("自主外展")
                  << QStringLiteral("单腿屈膝") << QStringLiteral("膝伸直抬腿");
        p.descriptions << QStringLiteral("仰卧位自行将手臂举向头顶")
                       << QStringLiteral("仰卧位自行将手臂向外打开")
                       << QStringLiteral("单腿主动屈膝再伸直，左右轮流")
                       << QStringLiteral("单腿保持伸直抬离床面，左右轮流");
        p.baseScore = 56;
        break;
    case 2:
        p.title = QStringLiteral("L2 坐姿辅助综合训练");
        p.subTitle = QStringLiteral("坐姿肩关节主动前屈、坐姿肩关节外展举、坐姿膝关节主动伸屈、坐姿上肢协调性训练");
        p.color = QStringLiteral("#F39C12");
        p.actionNames << QStringLiteral("坐姿肩关节主动前屈") << QStringLiteral("坐姿肩关节外展举")
                      << QStringLiteral("坐姿膝关节主动伸屈") << QStringLiteral("坐姿上肢协调性训练");
        p.targets << QStringLiteral("肩前屈") << QStringLiteral("肩外展")
                  << QStringLiteral("膝伸展") << QStringLiteral("双侧协调");
        p.descriptions << QStringLiteral("双手缓慢前屈上举至目标高度") << QStringLiteral("双手侧平举并平稳回落")
                       << QStringLiteral("单腿缓慢伸直并保持") << QStringLiteral("双手交替前推后拉");
        p.baseScore = 68;
        break;
    case 3:
        p.title = QStringLiteral("L3 站立主动综合训练");
        p.subTitle = QStringLiteral("站立肩关节全幅前屈上举、站立肩关节全幅外展、站立半蹲训练、站立单脚平衡训练");
        p.color = QStringLiteral("#2E86C1");
        p.actionNames << QStringLiteral("站立肩关节全幅前屈上举") << QStringLiteral("站立肩关节全幅外展")
                      << QStringLiteral("站立半蹲训练") << QStringLiteral("站立单脚平衡训练");
        p.targets << QStringLiteral("肩前屈") << QStringLiteral("膝关节控制")
                  << QStringLiteral("重心转移") << QStringLiteral("单脚平衡");
        p.descriptions << QStringLiteral("站立完成全幅前屈动作") << QStringLiteral("缓慢完成半蹲与起身")
                       << QStringLiteral("进行左右前后重心转移") << QStringLiteral("单脚抬起保持后换侧");
        p.baseScore = 78;
        break;
    default:
        p.title = QStringLiteral("L4 全幅主动综合训练");
        p.subTitle = QStringLiteral("太极拳式复合运动、站立上肢负重训练、站立单脚平衡进阶、站立身体旋转协调训练");
        p.color = QStringLiteral("#27AE60");
        p.actionNames << QStringLiteral("太极拳式复合运动") << QStringLiteral("站立上肢负重训练")
                      << QStringLiteral("站立单脚平衡进阶") << QStringLiteral("站立身体旋转协调训练");
        p.targets << QStringLiteral("全身协调") << QStringLiteral("肩力量控制")
                  << QStringLiteral("动态平衡") << QStringLiteral("躯干旋转");
        p.descriptions << QStringLiteral("完成连续复合动作组合") << QStringLiteral("在轻阻力下完成抬举控制")
                       << QStringLiteral("交替单脚抬起保持平衡") << QStringLiteral("双手平举完成左右转体");
        p.baseScore = 86;
        break;
    }
    return p;
}

void TrainingPage::applyTrainingPlan(const QJsonObject &payload)
{
    const int lvl = levelFromCode(payload.value(QStringLiteral("level")).toString());
    if (lvl < 1 || lvl > 4) {
        return;
    }

    LevelPlan plan;
    const QString levelName = payload.value(QStringLiteral("level_name")).toString();
    plan.title = levelName.isEmpty()
                     ? QStringLiteral("L%1 综合训练").arg(lvl)
                     : QStringLiteral("%1综合训练").arg(levelName);
    plan.subTitle = payload.value(QStringLiteral("description")).toString();
    plan.color = ScoreEngine::levelColor(lvl);
    plan.fromBackend = true;
    plan.bodyRegion = payload.value(QStringLiteral("body_region")).toString(
        QStringLiteral("upper"));
    plan.blockLabel = payload.value(QStringLiteral("block_label")).toString();
    plan.setupHint = payload.value(QStringLiteral("setup_hint")).toString();
    plan.suggestIntegration = payload.value(QStringLiteral("suggest_integration")).toBool(false);
    plan.hasIntegration = payload.value(QStringLiteral("has_integration")).toBool(false);

    m_suggestIntegration = plan.suggestIntegration;
    m_hasIntegrationBlock = plan.hasIntegration || integrationAvailableForLevel(lvl);
    m_setupHint = plan.setupHint;
    if (!plan.bodyRegion.isEmpty()) {
        m_currentBodyRegion = plan.bodyRegion;
    }

    const QJsonArray actions = payload.value(QStringLiteral("actions")).toArray();
    for (const QJsonValue &value : actions) {
        const QJsonObject obj = value.toObject();
        plan.actionIds.append(obj.value(QStringLiteral("id")).toString());
        plan.actionNames.append(obj.value(QStringLiteral("name")).toString());
        const int targetAngle = obj.value(QStringLiteral("target_angle")).toInt(0);
        if (targetAngle > 0) {
            plan.targets.append(QStringLiteral("目标角度 %1°").arg(targetAngle));
        } else {
            plan.targets.append(QStringLiteral("按语音提示完成"));
        }
        plan.descriptions.append(
            obj.value(QStringLiteral("description")).toString(
                QStringLiteral("请跟随语音完成该动作")));
    }

    if (plan.actionNames.isEmpty()) {
        return;
    }

    m_backendPlans[lvl] = plan;
    updateRegionTabs();
    if (!m_training && m_currentLevel == lvl) {
        syncPlanFromLevel();
        rebuildIntegratedPlan();
        updateBlockGuidance();
        refreshTrainingHud();
    }
}

void TrainingPage::requestTrainingPlan()
{
    if (!m_engine || !m_engine->isConnected()) {
        updateBlockGuidance();
        return;
    }
    QJsonObject extra;
    extra.insert(QStringLiteral("level"), currentLevelCode());
    extra.insert(QStringLiteral("body_region"), currentBodyRegionCode());
    m_engine->sendCommand(QStringLiteral("request_training_plan"), extra);
}

void TrainingPage::onEngineTrainingPlan(const QJsonObject &payload)
{
    applyTrainingPlan(payload);
}

int TrainingPage::stepIndexForActionId(const QString &actionId) const
{
    const LevelPlan plan = levelPlan(m_currentLevel);
    const int idx = plan.actionIds.indexOf(actionId);
    return idx >= 0 ? idx : m_currentStep;
}

void TrainingPage::syncPlanFromLevel()
{
    const LevelPlan plan = levelPlan(m_currentLevel);
    m_totalSteps = qMax(1, plan.actionNames.size());
    m_backendTotalActions = m_totalSteps;
}

void TrainingPage::rebuildIntegratedPlan()
{
    if (!m_actionContainer) {
        return;
    }

    QLayout *oldLay = m_actionContainer->layout();
    if (oldLay) {
        QLayoutItem *item = nullptr;
        while ((item = oldLay->takeAt(0)) != nullptr) {
            if (item->widget()) {
                item->widget()->setParent(nullptr);
            }
            delete item;
        }
        delete oldLay;
    }
    m_cards.clear();
    m_stepFrames.clear();
    m_stepBadges.clear();
    m_stepTexts.clear();

    const LevelPlan plan = levelPlan(m_currentLevel);
    const FontScale *fs = FontScale::instance();
    m_totalSteps = qMax(1, plan.actionNames.size());
    m_backendTotalActions = m_totalSteps;

    QVBoxLayout *boxLay = new QVBoxLayout(m_actionContainer);
    boxLay->setContentsMargins(0, 0, 0, 0);
    boxLay->setSpacing(0);

    QFrame *card = new QFrame(m_actionContainer);
    card->setObjectName(QStringLiteral("integratedTrainingCard"));
    card->setStyleSheet(
        "QFrame#integratedTrainingCard{background:#FFFFFF; border:1px solid #D0DDE8; border-radius:18px;}"
        "QLabel{background:transparent; border:none;}");
    QVBoxLayout *cardLay = new QVBoxLayout(card);
    cardLay->setContentsMargins(14, 14, 14, 14);
    cardLay->setSpacing(10);

    const QString cardTitle = plan.blockLabel.isEmpty()
                                  ? plan.title
                                  : QStringLiteral("%1 · %2").arg(plan.blockLabel, plan.title);
    QLabel *titleLbl = new QLabel(cardTitle, card);
    titleLbl->setWordWrap(true);
    titleLbl->setStyleSheet(
        QStringLiteral("font-size:%1px; font-weight:800; color:%2;")
            .arg(fs->px(16))
            .arg(plan.color));
    cardLay->addWidget(titleLbl);

    if (!plan.setupHint.isEmpty()) {
        QLabel *hintLbl = new QLabel(plan.setupHint, card);
        hintLbl->setWordWrap(true);
        hintLbl->setStyleSheet(
            QStringLiteral("font-size:%1px; color:#476A82; font-weight:600;").arg(fs->px(13)));
        cardLay->addWidget(hintLbl);
    } else if (!plan.subTitle.isEmpty()) {
        QLabel *subLbl = new QLabel(plan.subTitle, card);
        subLbl->setWordWrap(true);
        subLbl->setStyleSheet(QStringLiteral("font-size:%1px; color:#5D6D7E;").arg(fs->px(13)));
        cardLay->addWidget(subLbl);
    }

    QGridLayout *grid = new QGridLayout();
    grid->setHorizontalSpacing(10);
    grid->setVerticalSpacing(10);

    const int actionCount = plan.actionNames.size();
    for (int i = 0; i < actionCount; ++i) {
        QFrame *block = new QFrame(card);
        block->setObjectName(QStringLiteral("stepBlock"));
        block->setMinimumHeight(108);
        block->setStyleSheet(
            QStringLiteral("QFrame#stepBlock{background:#F8FBFF; border:1px solid #DCE6EE; border-radius:16px;}"));
        QVBoxLayout *blockLay = new QVBoxLayout(block);
        blockLay->setContentsMargins(12, 10, 12, 10);
        blockLay->setSpacing(6);

        QHBoxLayout *topLay = new QHBoxLayout();
        topLay->setSpacing(8);
        QLabel *badge = new QLabel(QString::number(i + 1), block);
        badge->setAlignment(Qt::AlignCenter);
        badge->setFixedSize(fs->largeMode() ? 36 : 30, fs->largeMode() ? 36 : 30);
        badge->setStyleSheet(
            QStringLiteral("background:%1; color:#FFFFFF; border-radius:15px; font-size:%2px; font-weight:900;")
                .arg(plan.color)
                .arg(fs->px(14)));
        topLay->addWidget(badge, 0, Qt::AlignTop);
        m_stepBadges.append(badge);

        QLabel *nameLbl = new QLabel(plan.actionNames.at(i), block);
        nameLbl->setWordWrap(true);
        nameLbl->setStyleSheet(
            QStringLiteral("font-size:%1px; color:#1B2631; font-weight:800;").arg(fs->px(15)));
        topLay->addWidget(nameLbl, 1);
        blockLay->addLayout(topLay);

        const QString target = i < plan.targets.size()
                                   ? plan.targets.at(i)
                                   : QStringLiteral("按语音提示完成");
        QLabel *targetLbl = new QLabel(QStringLiteral("目标：%1").arg(target), block);
        targetLbl->setWordWrap(true);
        targetLbl->setStyleSheet(
            QStringLiteral("font-size:%1px; color:#476A82; font-weight:600;").arg(fs->px(13)));
        blockLay->addWidget(targetLbl);

        const QString desc = i < plan.descriptions.size() ? plan.descriptions.at(i) : QString();
        QLabel *descLbl = new QLabel(desc, block);
        descLbl->setWordWrap(true);
        descLbl->setStyleSheet(QStringLiteral("font-size:%1px; color:#5D6D7E;").arg(fs->px(12)));
        blockLay->addWidget(descLbl);
        m_stepTexts.append(descLbl);
        m_stepFrames.append(block);

        grid->addWidget(block, i / 2, i % 2);
    }
    cardLay->addLayout(grid);

    QHBoxLayout *btnLay = new QHBoxLayout();
    btnLay->setSpacing(8);
    if (m_startBtn) {
        btnLay->addWidget(m_startBtn, 1);
    }
    if (m_pauseBtn) {
        btnLay->addWidget(m_pauseBtn, 1);
    }
    if (m_resumeBtn) {
        btnLay->addWidget(m_resumeBtn, 1);
    }
    if (m_stopBtn) {
        btnLay->addWidget(m_stopBtn, 1);
    }
    cardLay->addLayout(btnLay);

    if (m_actionProgress) {
        cardLay->addWidget(m_actionProgress);
    }

    boxLay->addWidget(card);
    if (!m_training) {
        m_currentStep = 0;
    }
    m_actionProgress->setValue(0);
    updateStepStates();
    updateTrainingGifForCurrentStep();
}

void TrainingPage::updateLevelTabs()
{
    for (int i = 0; i < 4; ++i) {
        m_levelBtns[i]->setChecked(i + 1 == m_currentLevel);
    }
    applyLevelTabStyles();
    m_selectedAction = m_currentLevel;
    m_hasIntegrationBlock = integrationAvailableForLevel(m_currentLevel);
    if (!m_hasIntegrationBlock && m_currentBodyRegion == QStringLiteral("integration")) {
        m_currentBodyRegion = QStringLiteral("upper");
    }
    updateRegionTabs();
    syncPlanFromLevel();
    rebuildIntegratedPlan();
    updateBlockGuidance();
}

void TrainingPage::refresh()
{
    if (!m_training) {
        updateLevelTabs();
    }
}

void TrainingPage::onActionClicked(int actionId)
{
    Q_UNUSED(actionId);
}

void TrainingPage::showActionDetail(int actionId)
{
    Q_UNUSED(actionId);
}

void TrainingPage::startIntegratedTraining()
{
    if (!m_training) {
        onStartTraining();
    }
}

QString TrainingPage::currentLevelCode() const
{
    return QStringLiteral("L%1").arg(m_currentLevel);
}

int TrainingPage::levelFromCode(const QString &code) const
{
    QString c = code.trimmed().toUpper();
    if (c.startsWith(QStringLiteral("L")) && c.size() >= 2) {
        bool ok = false;
        const int n = c.mid(1).toInt(&ok);
        if (ok && n >= 1 && n <= 4) {
            return n;
        }
    }
    return m_currentLevel;
}

void TrainingPage::onStartTraining()
{
    const LevelPlan plan = levelPlan(m_currentLevel);
    m_training = true;
    m_engineMode = m_engine && m_engine->isConnected();
    m_score = ScoreResult();
    m_pendingSave = false;
    m_sequenceElapsed = 0;
    m_currentStep = 0;
    m_totalSteps = qMax(1, plan.actionNames.size());
    m_backendTotalActions = m_totalSteps;
    m_actionProgress->setValue(0);
    m_startBtn->hide();
    m_pauseBtn->show();
    m_pauseBtn->setEnabled(m_engineMode);
    m_resumeBtn->hide();
    m_stopBtn->show();
    for (int i = 0; i < 4; ++i) {
        if (m_levelBtns[i]) {
            m_levelBtns[i]->setEnabled(false);
        }
    }
    for (int i = 0; i < 3; ++i) {
        if (m_regionBtns[i]) {
            m_regionBtns[i]->setEnabled(false);
        }
    }
    updateStepStates();
    updateTrainingGifForCurrentStep();

    if (m_engineMode) {
        if (m_sequenceTimer) {
            m_sequenceTimer->stop();
        }
        if (m_guidanceText) {
            m_guidanceText->show();
            m_guidanceText->setText(QStringLiteral("正在向后端发送开始训练指令…"));
        }
        if (m_visionPreview) {
            m_visionPreview->setTopLeftText(QStringLiteral("准备中…"));
        }
        sendTrainingEngineCommand(QStringLiteral("start_training"));
        return;
    }

    if (m_guidanceText) {
        m_guidanceText->show();
        m_guidanceText->setText(QStringLiteral("未连接后端，请先启动 rehab-coach-rknn 后再训练。"));
    }
    m_training = false;
    m_startBtn->show();
    m_pauseBtn->hide();
    m_resumeBtn->hide();
    m_stopBtn->hide();
    for (int i = 0; i < 4; ++i) {
        if (m_levelBtns[i]) {
            m_levelBtns[i]->setEnabled(true);
        }
    }
    for (int i = 0; i < 3; ++i) {
        if (m_regionBtns[i]) {
            m_regionBtns[i]->setEnabled(i != 2 || m_hasIntegrationBlock);
        }
    }
    updateRegionTabs();
}

void TrainingPage::onSequenceTick()
{
    if (!m_training || m_engineMode) {
        return;
    }

    ++m_sequenceElapsed;
    const int totalSeconds = qMax(1, m_stepSeconds * m_totalSteps);
    m_currentStep = qMin(m_totalSteps - 1, m_sequenceElapsed / m_stepSeconds);
    const int progress = qBound(0, qRound(m_sequenceElapsed * 100.0 / totalSeconds), 100);
    m_actionProgress->setValue(progress);
    updateStepStates();
    updateTrainingGifForCurrentStep();

    if (m_sequenceElapsed >= totalSeconds) {
        finishIntegratedTraining(true);
    }
}

void TrainingPage::onStopTraining()
{
    if (m_engineMode && m_engine) {
        m_pendingSave = true;
        sendTrainingEngineCommand(QStringLiteral("stop_training"));
        return;
    }
    finishIntegratedTraining(false);
}

void TrainingPage::finishIntegratedTraining(bool saveResult)
{
    if (m_sequenceTimer) {
        m_sequenceTimer->stop();
    }
    m_training = false;
    m_engineMode = false;
    m_paused = false;
    m_startBtn->show();
    m_pauseBtn->hide();
    m_resumeBtn->hide();
    m_stopBtn->hide();
    for (int i = 0; i < 4; ++i) {
        if (m_levelBtns[i]) {
            m_levelBtns[i]->setEnabled(true);
        }
    }
    for (int i = 0; i < 3; ++i) {
        if (m_regionBtns[i]) {
            m_regionBtns[i]->setEnabled(i != 2 || m_hasIntegrationBlock);
        }
    }
    updateRegionTabs();

    if (m_visionPreview) {
        m_visionPreview->setTopLeftText(QString());
        m_visionPreview->clearRightCameraGif();
    }

    if (saveResult) {
        completeTrainingWithScore();
    } else if (!m_pendingSave) {
        m_currentStep = 0;
        m_actionProgress->setValue(0);
        updateStepStates();
        updateBlockGuidance();
    }
}

void TrainingPage::completeTrainingWithScore()
{
    const LevelPlan plan = levelPlan(m_currentLevel);
    if (m_score.compositeScore <= 0 && m_score.blockScores.isEmpty()) {
        return;
    }

    m_actionProgress->setValue(qMax(m_actionProgress->value(), 100));
    m_currentStep = m_totalSteps;
    updateStepStates();

    const QString title = plan.fromBackend ? plan.title : plan.title;
    const int completion = qBound(0, m_actionProgress->value(), 100);
    emit trainingCompleted(title, m_score, completion);
    m_pendingSave = false;
}

void TrainingPage::updateStepStates()
{
    const LevelPlan plan = levelPlan(m_currentLevel);
    const FontScale *fs = FontScale::instance();
    const bool completed = (!m_training && m_currentStep >= m_totalSteps
                              && m_actionProgress && m_actionProgress->value() >= 100);

    for (int i = 0; i < m_stepBadges.size(); ++i) {
        QLabel *badge = m_stepBadges.at(i);
        QLabel *text = m_stepTexts.value(i, nullptr);
        QFrame *frame = m_stepFrames.value(i, nullptr);
        if (!badge || !frame) {
            continue;
        }

        QString badgeBg = QStringLiteral("#D0DDE8");
        QString badgeFg = QStringLiteral("#1A5276");
        QString frameStyle = QStringLiteral(
            "QFrame#stepBlock{background:#F8FBFF; border:1px solid #DCE6EE; border-radius:16px;}");
        QString suffix;

        if (m_training) {
            if (i < m_currentStep) {
                badgeBg = QStringLiteral("#27AE60");
                badgeFg = QStringLiteral("#FFFFFF");
                frameStyle = QStringLiteral(
                    "QFrame#stepBlock{background:#F1FBF5; border:2px solid #27AE60; border-radius:16px;}");
                suffix = QStringLiteral("（已完成）");
            } else if (i == m_currentStep) {
                badgeBg = plan.color;
                badgeFg = QStringLiteral("#FFFFFF");
                frameStyle = QStringLiteral(
                    "QFrame#stepBlock{background:#FFF8EF; border:2px solid %1; border-radius:16px;}")
                    .arg(plan.color);
                suffix = QStringLiteral("（训练中）");
            }
        } else if (completed) {
            badgeBg = QStringLiteral("#27AE60");
            badgeFg = QStringLiteral("#FFFFFF");
            frameStyle = QStringLiteral(
                "QFrame#stepBlock{background:#F1FBF5; border:2px solid #27AE60; border-radius:16px;}");
            suffix = QStringLiteral("（已完成）");
        }

        badge->setStyleSheet(
            QStringLiteral("background:%1; color:%2; border-radius:15px; font-size:%3px; font-weight:900;")
                .arg(badgeBg, badgeFg, QString::number(fs->px(14))));
        frame->setStyleSheet(frameStyle);
        if (text && i < plan.descriptions.size()) {
            text->setText(plan.descriptions.at(i) + suffix);
        }
    }

    if (m_training && m_currentStep < plan.actionNames.size() && m_guidanceText) {
        m_guidanceText->show();
        m_guidanceText->setText(
            QStringLiteral("当前动作 %1/%2：%3")
                .arg(m_currentStep + 1)
                .arg(plan.actionNames.size())
                .arg(plan.actionNames.at(m_currentStep)));
        return;
    }

    if (!m_training) {
        m_guidanceText->hide();
        updateBlockGuidance();
    }
}

void TrainingPage::sendTrainingEngineCommand(const QString &command)
{
    if (!m_engine) {
        return;
    }
    QJsonObject extra;
    extra.insert(QStringLiteral("level"), currentLevelCode());
    extra.insert(QStringLiteral("body_region"), currentBodyRegionCode());
    m_engine->sendCommand(command, extra);
}

void TrainingPage::onEngineConnectionChanged(bool connected)
{
    if (!m_engineStatus) {
        return;
    }
    if (connected) {
        m_engineStatus->setText(QStringLiteral("引擎：已连接"));
        m_engine->sendCommand(QStringLiteral("request_status"));
        requestTrainingPlan();
    } else {
        m_engineStatus->setText(QStringLiteral("引擎：未连接"));
    }
    refreshTrainingHud();
}

void TrainingPage::onEngineActionStatus(const QJsonObject &payload)
{
    if (!m_training) {
        return;
    }

    const int rep = payload.value(QStringLiteral("rep_count")).toInt(-1);
    const int target = payload.value(QStringLiteral("target_reps")).toInt(0);
    const double angle = payload.value(QStringLiteral("current_angle")).toDouble(0);
    const QString metricName = payload.value(QStringLiteral("metric_name")).toString();
    const QString metricUnit = payload.value(QStringLiteral("metric_unit")).toString();
    Q_UNUSED(payload.value(QStringLiteral("state")).toString());

    if (target > 0 && rep >= 0) {
        const int actionPct = qBound(0, qRound(rep * 100.0 / target), 100);
        const int base = m_totalSteps > 0
                             ? qRound(m_currentStep * 100.0 / m_totalSteps)
                             : 0;
        const int span = m_totalSteps > 0 ? qMax(1, 100 / m_totalSteps) : 100;
        m_actionProgress->setValue(qBound(0, base + actionPct * span / 100, 100));
    }

    const QString actionId = payload.value(QStringLiteral("action_id")).toString();
    const QString actionName = payload.value(QStringLiteral("action_name")).toString();
    const int stepIdx = stepIndexForActionId(actionId);
    if (stepIdx >= 0 && stepIdx != m_currentStep) {
        m_currentStep = stepIdx;
        updateStepStates();
    }

    const QString displayName = actionName.isEmpty() ? actionId : actionName;
    updateTrainingOverlay(displayName, rep, target, angle, metricName, metricUnit);
    updateTrainingGifForAction(displayName);

    if (m_guidanceText) {
        m_guidanceText->hide();
    }
}

void TrainingPage::onEngineTrainingProgress(const QJsonObject &payload)
{
    if (!m_training) {
        return;
    }

    const int completed = payload.value(QStringLiteral("completed_actions")).toInt(0);
    const int total = payload.value(QStringLiteral("total_actions")).toInt(m_totalSteps);
    m_backendTotalActions = qMax(1, total);
    m_totalSteps = qMax(1, total);
    m_currentStep = qBound(0, completed, m_totalSteps);

    const QString currentName = payload.value(QStringLiteral("current_action_name")).toString();
    if (!currentName.isEmpty()) {
        updateTrainingOverlay(currentName, -1, 0, 0);
        updateTrainingGifForAction(currentName);
    } else {
        updateTrainingGifForCurrentStep();
    }

    const double rate = payload.value(QStringLiteral("completion_rate")).toDouble(0);
    if (rate > 0) {
        m_actionProgress->setValue(qBound(0, qRound(rate * 100.0), 100));
    }
    updateStepStates();
}

void TrainingPage::onEngineTrainingState(const QJsonObject &payload)
{
    const QString phase = payload.value(QStringLiteral("phase")).toString();
    const QString message = payload.value(QStringLiteral("message")).toString();

    if (m_guidanceText && !message.isEmpty()) {
        m_guidanceText->show();
        m_guidanceText->setText(message);
    }

    if (phase == QStringLiteral("running") && m_training) {
        m_paused = false;
        if (m_pauseBtn) {
            m_pauseBtn->show();
            m_pauseBtn->setEnabled(true);
        }
        if (m_resumeBtn) {
            m_resumeBtn->hide();
        }
        if (m_guidanceText) {
            m_guidanceText->setText(QStringLiteral("训练进行中，请跟随语音完成动作。"));
        }
        return;
    }

    if (phase == QStringLiteral("paused") && m_training) {
        m_paused = true;
        if (m_pauseBtn) {
            m_pauseBtn->hide();
        }
        if (m_resumeBtn) {
            m_resumeBtn->show();
        }
        if (m_guidanceText) {
            m_guidanceText->setText(QStringLiteral("训练已暂停，点击继续恢复。"));
        }
        return;
    }

    if (phase == QStringLiteral("block_complete")) {
        const QString suggest = payload.value(QStringLiteral("suggest_next_region")).toString();
        if (m_guidanceText && !message.isEmpty()) {
            m_guidanceText->show();
            m_guidanceText->setText(message);
        }
        if (suggest == QStringLiteral("lower") && m_regionBtns[1]) {
            m_regionBtns[1]->setStyleSheet(
                ElderUx::levelBtnStyle(QStringLiteral("#27AE60"), false));
        }
        return;
    }

    if (phase == QStringLiteral("stopped")) {
        if (m_training) {
            m_pendingSave = true;
            finishIntegratedTraining(false);
        }
    }
}

void TrainingPage::onEngineScoring(const QJsonObject &payload)
{
    m_score = ScoreEngine::fromEnginePayload(payload);
    const int lvl = levelFromCode(payload.value(QStringLiteral("level")).toString());
    if (lvl >= 1 && lvl <= 4) {
        m_currentLevel = lvl;
    }

    const QString source = payload.value(QStringLiteral("source")).toString();
    const bool trainingScore = source == QStringLiteral("training")
            || payload.contains(QStringLiteral("action_scores"));
    if (trainingScore && m_pendingSave) {
        completeTrainingWithScore();
        return;
    }

    if (!m_training && source == QStringLiteral("assessment")) {
        onScoreReady(m_score);
    }
}

void TrainingPage::onEngineSessionSummary(const QString &text)
{
    if (m_guidanceText) {
        m_guidanceText->show();
        m_guidanceText->setText(text);
    }
}

void TrainingPage::onEngineCorrection(const QJsonObject &payload)
{
    const QJsonArray arr = payload.value(QStringLiteral("corrections")).toArray();
    if (arr.isEmpty() || !m_guidanceText) {
        return;
    }
    const QJsonObject first = arr.first().toObject();
    m_guidanceText->show();
    m_guidanceText->setText(first.value(QStringLiteral("message")).toString());
}

void TrainingPage::onEngineEncouragement(const QString &text)
{
    if (m_guidanceText && !text.isEmpty()) {
        m_guidanceText->show();
        m_guidanceText->setText(text);
    }
}

void TrainingPage::onEngineVisionPreview(const QJsonObject &payload)
{
    if (m_visionPreview) {
        m_visionPreview->updatePreview(payload);
    }
    updateVisionMetricsFromPreview(payload);
}

void TrainingPage::updateVisionMetricsFromPreview(const QJsonObject &payload)
{
    if (!m_visionPreview) {
        return;
    }

    const QString warning = payload.value(QStringLiteral("vision_warning")).toString();
    const QString status = payload.value(QStringLiteral("vision_status")).toString();
    const bool hasQuality = payload.contains(QStringLiteral("vision_quality"));

    if (!hasQuality && warning.isEmpty() && status.isEmpty()) {
        return;
    }

    const QString statusText = ElderUx::visionStatusLabel(status);
    QString body;
    if (hasQuality) {
        const double quality = payload.value(QStringLiteral("vision_quality")).toDouble(0);
        body = QStringLiteral("画面质量 %1%").arg(qRound(quality * 100.0));
    }

    m_visionPreview->setBottomBarText(
        ElderUx::formatVisionLine(statusText, body, warning));
}

void TrainingPage::onPauseTraining()
{
    if (!m_training || !m_engineMode) {
        return;
    }
    sendTrainingEngineCommand(QStringLiteral("pause_training"));
}

void TrainingPage::onResumeTraining()
{
    if (!m_training || !m_engineMode) {
        return;
    }
    sendTrainingEngineCommand(QStringLiteral("resume_training"));
}

void TrainingPage::onScoreReady(const ScoreResult &result)
{
    m_score = result;
    if (!m_training && result.level >= 1 && result.level <= 4) {
        m_currentLevel = result.level;
        updateLevelTabs();
    }
}

void TrainingPage::onFusionFrame(const FusionFrame &frame)
{
    Q_UNUSED(frame);
}

void TrainingPage::onGuidanceReady(const QString &text)
{
    if (m_guidanceText && !text.isEmpty()) {
        m_guidanceText->show();
        m_guidanceText->setText(text);
    }
}
