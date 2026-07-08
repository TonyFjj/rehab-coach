#include "assessmentpage.h"
#include "ipc/enginebridge.h"
#include "widgets/visionpreviewwidget.h"
#include "utils/elderux.h"
#include "utils/fontscale.h"

#include "models/datastorage.h"
#include <QVBoxLayout>
#include <QDateTime>
#include <QHBoxLayout>
#include <QScrollArea>
#include <QFrame>
#include <QJsonArray>
#include <QJsonObject>
#include <QGuiApplication>
#include <QScreen>
#include <QStackedWidget>
#include <QtGlobal>

AssessmentPage::AssessmentPage(QWidget *parent) : QWidget(parent)
{
    m_timer = new QTimer(this);
    m_timer->setInterval(1000);
    connect(m_timer, &QTimer::timeout, this, &AssessmentPage::onTick);
    setupUI();
    loadStoredAssessment();
}

void AssessmentPage::setEngineBridge(EngineBridge *engine)
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
    connect(m_engine, &EngineBridge::scoringReceived,
            this, &AssessmentPage::onEngineScoring);
    connect(m_engine, &EngineBridge::connectionChanged,
            this, &AssessmentPage::onEngineConnectionChanged);
    connect(m_engine, &EngineBridge::assessmentPlanReceived,
            this, &AssessmentPage::onEngineAssessmentPlan);
    connect(m_engine, &EngineBridge::assessmentPhaseReceived,
            this, &AssessmentPage::onEngineAssessmentPhase);
    connect(m_engine, &EngineBridge::visionPreviewReceived,
            this, &AssessmentPage::onEngineVisionPreview);
}

void AssessmentPage::onEngineConnectionChanged(bool connected)
{
    if (connected && m_engine) {
        m_engine->sendCommand(QStringLiteral("request_status"));
        requestAssessmentPlan();
    }
}

void AssessmentPage::requestAssessmentPlan()
{
    if (m_engine && m_engine->isConnected()) {
        m_engine->sendCommand(QStringLiteral("request_assessment_plan"));
    }
}

void AssessmentPage::onEngineAssessmentPlan(const QJsonObject &payload)
{
    m_totalSeconds = qMax(30, payload.value(QStringLiteral("total_estimated_seconds")).toInt(60));
    const int collectFromPlan = payload.value(QStringLiteral("collect_seconds")).toInt(0);
    if (collectFromPlan > 0) {
        m_collectSeconds = collectFromPlan;
    } else {
        const QJsonArray actions = payload.value(QStringLiteral("actions")).toArray();
        if (!actions.isEmpty()) {
            const QJsonObject act = actions.at(0).toObject();
            const int totalDur = act.value(QStringLiteral("total_duration")).toInt(0);
            const int dur = act.value(QStringLiteral("duration")).toInt(0);
            m_collectSeconds = qMax(30, totalDur > 0 ? totalDur : dur);
        }
    }
    m_totalActions = qMax(1, payload.value(QStringLiteral("actions")).toArray().size());
    if (!m_engineMode) {
        m_progress->setRange(0, m_collectSeconds);
        m_progress->setValue(0);
    }
    showActionPlan(payload);
}

void AssessmentPage::showActionPlan(const QJsonObject &payload)
{
    const QString intro = payload.value(QStringLiteral("intro_text")).toString();
    const QJsonArray actions = payload.value(QStringLiteral("actions")).toArray();

    if (!intro.isEmpty()) {
        m_voiceHint->setText(intro);
    } else {
        m_voiceHint->setText(QStringLiteral("请同时看大字字幕并听语音。"));
    }

    QStringList lines;
    lines << QStringLiteral("评估包含 %1 个动作：").arg(actions.size());
    for (int i = 0; i < actions.size(); ++i) {
        const QJsonObject act = actions.at(i).toObject();
        const QString name = act.value(QStringLiteral("name")).toString();
        const int dur = act.value(QStringLiteral("duration")).toInt(0);
        lines << QStringLiteral("%1. %2（%3 秒）").arg(i + 1).arg(name).arg(dur);
    }
    m_actionList->setText(lines.join('\n'));
    if (!m_engineMode && !m_hasStoredResult) {
        m_instruction->setText(
            QStringLiteral("点击下方「进入评估」后，将切换到摄像头界面并开始动作采集。"));
    }
}

void AssessmentPage::onEngineAssessmentPhase(const QJsonObject &payload)
{
    if (!m_engineMode) {
        return;
    }
    applyAssessmentPhase(payload);
}

void AssessmentPage::applyAssessmentPhase(const QJsonObject &payload)
{
    const QString phase = payload.value(QStringLiteral("phase")).toString();
    const QString instruction = payload.value(QStringLiteral("instruction")).toString();
    const QString actionName = payload.value(QStringLiteral("action_name")).toString();
    const int actionIndex = payload.value(QStringLiteral("action_index")).toInt(0);
    const int duration = payload.value(QStringLiteral("duration")).toInt(0);
    const bool hasVisionLive = payload.contains(QStringLiteral("vision_completion"))
                               || payload.contains(QStringLiteral("vision_quality"))
                               || payload.contains(QStringLiteral("vision_current_angle"));

    // 采集中视觉实时推送：只更新画面指标，不重置倒计时
    if (phase == QStringLiteral("collecting") && m_collectActive && hasVisionLive
        && actionIndex <= 0 && actionName.isEmpty() && duration <= 0) {
        updateVisionMetricsFromPayload(payload);
        return;
    }

    const bool phaseChanged = (phase != m_lastPhase);
    m_lastPhase = phase;

    m_currentActionIndex = actionIndex;
    m_totalActions = qMax(1, payload.value(QStringLiteral("total_actions")).toInt(m_totalActions));
    m_phaseDuration = qMax(0, duration);
    if (phaseChanged) {
        m_phaseElapsed = 0;
    }

    if (phase != QStringLiteral("collecting")) {
        m_collectActive = false;
    }

    if (!instruction.isEmpty()) {
        m_sessionSubtitle->setText(instruction);
        refreshSessionSubtitleLayout();
    }

    if (phase == QStringLiteral("intro")) {
        m_sessionVoiceHint->setText(QStringLiteral("🔊 请听语音，并阅读下方大字字幕"));
        m_sessionActionLabel->setText(QStringLiteral("准备开始"));
        m_sessionCountdown->setText(QStringLiteral("开始"));
        m_sessionProgress->setRange(0, m_collectSeconds);
        m_sessionProgress->setValue(0);
        refreshSessionChrome(phase);
        updateVisionPreviewHeight();
        return;
    }

    if (phase == QStringLiteral("precheck")) {
        m_sessionCountdown->setText(QStringLiteral("预检"));
        m_sessionProgress->setRange(0, qMax(1, m_phaseDuration));
        m_sessionProgress->setValue(0);
        refreshSessionChrome(phase);
        updateVisionMetricsFromPayload(payload);
        updateVisionPreviewHeight();
        return;
    }

    if (phase == QStringLiteral("action")) {
        m_sessionVoiceHint->setText(QStringLiteral("🔊 正在播报动作说明，请仔细听并阅读字幕"));
        m_sessionActionLabel->setText(
            QStringLiteral("动作 %1/%2：%3")
                .arg(m_currentActionIndex)
                .arg(m_totalActions)
                .arg(actionName));
        m_sessionCountdown->setText(QStringLiteral("听指令"));
        m_sessionProgress->setRange(0, 100);
        m_sessionProgress->setValue(0);
        refreshSessionChrome(phase);
        updateVisionPreviewHeight();
        return;
    }

    if (phase == QStringLiteral("collecting")) {
        const int collectDur = m_phaseDuration > 0 ? m_phaseDuration : m_collectSeconds;
        if (phaseChanged || !m_collectActive) {
            m_collectSeconds = collectDur;
            m_collectActive = true;
            m_phaseElapsed = 0;
            m_sessionProgress->setRange(0, m_collectSeconds);
            m_sessionProgress->setValue(0);
        }

        const QString subPhase = payload.value(QStringLiteral("sub_phase")).toString();
        if (subPhase == QStringLiteral("prep")) {
            m_sessionVoiceHint->setText(QStringLiteral("▶ 准备：请保持双手自然下垂"));
            m_sessionActionLabel->setText(QStringLiteral("准备 %1/%2：%3")
                                       .arg(m_currentActionIndex)
                                       .arg(m_totalActions)
                                       .arg(actionName));
        } else if (subPhase == QStringLiteral("motion")) {
            m_sessionVoiceHint->setText(QStringLiteral("▶ 请侧平举并举过头顶（手心朝外）"));
            m_sessionActionLabel->setText(QStringLiteral("进行中 %1/%2：%3")
                                       .arg(m_currentActionIndex)
                                       .arg(m_totalActions)
                                       .arg(actionName));
        } else {
            m_sessionVoiceHint->setText(QStringLiteral("▶ 三十秒连续动作：下垂 → 举过顶 → 保持"));
            m_sessionActionLabel->setText(QStringLiteral("进行中 %1/%2：%3")
                                       .arg(m_currentActionIndex)
                                       .arg(m_totalActions)
                                       .arg(actionName));
        }
        if (phaseChanged || !m_timer->isActive()) {
            const int remain = qMax(0, m_collectSeconds - m_phaseElapsed);
            m_sessionCountdown->setText(formatCountdown(remain));
            if (m_engineMode) {
                m_timer->start();
            }
        }
        updateVisionMetricsFromPayload(payload);
        refreshSessionChrome(phase);
        updateVisionPreviewHeight();
        return;
    }

    if (phase == QStringLiteral("rest")) {
        m_collectActive = false;
        m_sessionProgress->setValue(0);
        m_sessionVoiceHint->setText(QStringLiteral("休息中，等待下一个动作"));
        m_sessionActionLabel->setText(QStringLiteral("动作间休息"));
        m_sessionSubtitle->setText(
            instruction.isEmpty()
                ? QStringLiteral("请放松肩膀和手臂，准备下一个动作。")
                : instruction);
        m_sessionCountdown->setText(formatCountdown(qMax(1, m_phaseDuration)));
        refreshSessionChrome(phase);
        return;
    }

    if (phase == QStringLiteral("analyzing")) {
        m_collectActive = false;
        m_sessionProgress->setValue(m_collectSeconds);
        m_sessionVoiceHint->setText(QStringLiteral("请保持安静"));
        m_sessionActionLabel->setText(QStringLiteral("分析中"));
        m_sessionCountdown->setText(QStringLiteral("分析"));
        m_enterBtn->setText(QStringLiteral("分析中…"));
        refreshSessionChrome(phase);
        return;
    }

    if (phase == QStringLiteral("done")) {
        m_collectActive = false;
        m_sessionProgress->setValue(m_collectSeconds);
        m_sessionVoiceHint->setText(QStringLiteral("评估完成"));
        m_sessionActionLabel->setText(QStringLiteral("评估完成"));
        m_sessionCountdown->setText(QStringLiteral("完成"));
        refreshSessionChrome(phase);
        updateVisionPreviewHeight();
        return;
    }

    refreshSessionChrome(phase);
    updateVisionPreviewHeight();
}

QString AssessmentPage::formatCountdown(int seconds) const
{
    const int s = qMax(0, seconds);
    return QStringLiteral("%1:%2")
        .arg(s / 60, 2, 10, QChar('0'))
        .arg(s % 60, 2, 10, QChar('0'));
}

void AssessmentPage::onEngineScoring(const QJsonObject &payload)
{
    const QString source = payload.value(QStringLiteral("source")).toString();
    if (m_engineMode || source == QStringLiteral("assessment")) {
        const bool liveAssessment = m_engineMode;
        if (m_engineMode) {
            m_timer->stop();
            m_engineMode = false;
        }
        m_visionFusionNote = buildVisionFusionNote(payload);
        applyAssessmentResult(ScoreEngine::fromEnginePayload(payload), liveAssessment);
        showIntroPage();
    }
}

void AssessmentPage::onEngineVisionPreview(const QJsonObject &payload)
{
    if (m_pageStack && m_pageStack->currentWidget() != m_sessionPage) {
        return;
    }
    if (m_visionPreview) {
        m_visionPreview->updatePreview(payload);
    }
    // 采集中底部指标由 assessment_phase 推送（约 0.5s）；预览帧带 quality 会与之交替导致闪烁
    if (!m_collectActive) {
        updateVisionMetricsFromPayload(payload);
    }
}

void AssessmentPage::updateVisionMetricsFromPayload(const QJsonObject &payload)
{
    if (!m_visionPreview) {
        return;
    }

    const QString warning = payload.value(QStringLiteral("vision_warning")).toString();
    const QString status = payload.value(QStringLiteral("vision_status")).toString();
    const bool hasCompletion = payload.contains(QStringLiteral("vision_completion"));
    const bool hasQuality = payload.contains(QStringLiteral("vision_quality"));

    if (!hasCompletion && !hasQuality && warning.isEmpty() && status.isEmpty()) {
        return;
    }

    const QString statusText = ElderUx::visionStatusLabel(status);
    QString body;
    if (hasCompletion) {
        const double completion = payload.value(QStringLiteral("vision_completion")).toDouble(0);
        const double accuracy = payload.value(QStringLiteral("vision_accuracy")).toDouble(0);
        const double curAngle = payload.value(QStringLiteral("vision_current_angle")).toDouble(0);
        const double maxAngle = payload.value(QStringLiteral("vision_max_angle")).toDouble(0);
        body = QStringLiteral("完成 %1%  准确 %2%  当前 %3°  峰值 %4°")
            .arg(qRound(completion * 100.0))
            .arg(qRound(accuracy * 100.0))
            .arg(curAngle, 0, 'f', 0)
            .arg(maxAngle, 0, 'f', 0);
    } else if (hasQuality && !m_collectActive) {
        const double quality = payload.value(QStringLiteral("vision_quality")).toDouble(0);
        body = QStringLiteral("画面质量 %1%").arg(qRound(quality * 100.0));
    } else if (!hasCompletion) {
        return;
    }

    m_visionPreview->setBottomBarText(
        ElderUx::formatVisionLine(statusText, body, warning));
}

void AssessmentPage::showIntroPage()
{
    if (m_pageStack) {
        m_pageStack->setCurrentWidget(m_introPage);
    }
}

void AssessmentPage::showSessionPage()
{
    if (m_pageStack) {
        m_pageStack->setCurrentWidget(m_sessionPage);
    }
    updateVisionPreviewHeight();
    refreshSessionChrome(m_lastPhase.isEmpty() ? QStringLiteral("intro") : m_lastPhase);
    if (m_visionPreview) {
        m_visionPreview->setTopRightText(QStringLiteral("健康评估\n摄像头采集中"));
    }
}

void AssessmentPage::beginAssessmentSession()
{
    m_hasStoredResult = false;
    m_sessionElapsed = 0;
    m_phaseElapsed = 0;
    m_collectActive = false;
    m_lastPhase.clear();
    m_sessionProgress->setRange(0, m_collectSeconds);
    m_sessionProgress->setValue(0);
    m_sessionCountdown->setText(QStringLiteral("00:00"));
    m_enterBtn->setEnabled(false);
    m_enterBtn->setText(QStringLiteral("评估中…"));

    if (m_engine && m_engine->isConnected()) {
        m_engineMode = true;
        m_sessionVoiceHint->setText(QStringLiteral("已连接后端：请同时看大字字幕 + 听扬声器"));
        m_sessionSubtitle->setText(QStringLiteral("评估即将开始，请听开场说明…"));
        QJsonObject extra;
        extra.insert(QStringLiteral("force"), true);
        m_engine->sendCommand(QStringLiteral("start_assessment"), extra);
        m_timer->start();
        return;
    }

    m_engineMode = false;
    m_enterBtn->setEnabled(true);
    m_enterBtn->setText(QStringLiteral("进入评估"));
    showIntroPage();
    m_instruction->setText(QStringLiteral("未连接后端，请先启动 rehab-coach-rknn 后再评估。"));
}

QString AssessmentPage::buildVisionFusionNote(const QJsonObject &payload) const
{
    QStringList parts;
    const QJsonObject lr = payload.value(QStringLiteral("lr_scores")).toObject();
    if (!lr.isEmpty()) {
        const double left = lr.value(QStringLiteral("left")).toDouble(0);
        const double right = lr.value(QStringLiteral("right")).toDouble(0);
        if (left > 0 || right > 0) {
            parts << QStringLiteral("左右手：左 %1 分，右 %2 分")
                       .arg(left, 0, 'f', 1)
                       .arg(right, 0, 'f', 1);
        }
    } else {
        const QString lrNote = payload.value(QStringLiteral("lr_note")).toString().trimmed();
        if (!lrNote.isEmpty()) {
            parts << lrNote;
        }
    }

    const QJsonObject va = payload.value(QStringLiteral("vision_assessment")).toObject();
    if (va.isEmpty()) {
        return parts.isEmpty()
            ? QStringLiteral("评估分数来自 IMU 六维测评")
            : parts.join(QStringLiteral("\n"));
    }

    const double completion = va.value(QStringLiteral("completion_coef")).toDouble(0);
    const double accuracy = va.value(QStringLiteral("accuracy_coef")).toDouble(0);
    const double maxAngle = va.value(QStringLiteral("max_angle")).toDouble(0);
    const double quality = va.value(QStringLiteral("quality_score")).toDouble(0);
    parts << QStringLiteral(
        "评估分数来自 IMU；视觉参考 完成度 %1% 准确度 %2% 峰值 %3°（画面质量 %4%，不参与计分）")
               .arg(qRound(completion * 100.0))
               .arg(qRound(accuracy * 100.0))
               .arg(maxAngle, 0, 'f', 0)
               .arg(qRound(quality * 100.0));
    return parts.join(QStringLiteral("\n"));
}

void AssessmentPage::setupUI()
{
    QVBoxLayout *outer = new QVBoxLayout(this);
    outer->setContentsMargins(0, 0, 0, 4);
    outer->setSpacing(0);

    m_pageStack = new QStackedWidget(this);
    outer->addWidget(m_pageStack, 1);

    // —— 介绍页：无摄像头，查看说明与历史结果 ——
    m_introPage = new QWidget();
    QVBoxLayout *introOuter = new QVBoxLayout(m_introPage);
    introOuter->setContentsMargins(0, 0, 0, 0);
    introOuter->setSpacing(0);

    QScrollArea *scroll = new QScrollArea(m_introPage);
    scroll->setWidgetResizable(true);
    scroll->setFrameShape(QFrame::NoFrame);
    scroll->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);

    QWidget *content = new QWidget();
    QVBoxLayout *lay = new QVBoxLayout(content);
    lay->setContentsMargins(12, 6, 12, 6);
    lay->setSpacing(6);

    m_title = new QLabel(QStringLiteral("健康评估"));
    m_title->setStyleSheet("font-size:20px; font-weight:bold; color:#1A5276; border:none;");
    lay->addWidget(m_title);

    m_voiceHint = new QLabel(QStringLiteral("请同时看大字字幕并听语音。"));
    m_voiceHint->setWordWrap(true);
    m_voiceHint->setAlignment(Qt::AlignLeft | Qt::AlignTop);
    m_voiceHint->setSizePolicy(QSizePolicy::Preferred, QSizePolicy::Minimum);
    m_voiceHint->setStyleSheet(
        "font-size:14px; font-weight:bold; color:#1A5276; background:#F8FBFF; border:1px solid #D0DDE8;"
        "border-radius:8px; padding:4px 10px;");
    lay->addWidget(m_voiceHint);

    m_actionList = new QLabel(QStringLiteral("连接后端后将显示评估动作说明…"));
    m_actionList->setWordWrap(true);
    m_actionList->setSizePolicy(QSizePolicy::Preferred, QSizePolicy::Minimum);
    m_actionList->setStyleSheet(
        "font-size:13px; color:#4A4A4A; background:#FFFFFF; border:1px solid #E0E8EF;"
        "border-radius:8px; padding:6px 10px; line-height:140%;");
    lay->addWidget(m_actionList);

    m_progress = new QProgressBar();
    m_progress->setRange(0, m_collectSeconds);
    m_progress->setValue(0);
    m_progress->setFixedHeight(14);
    m_progress->hide();
    lay->addWidget(m_progress);

    m_countdown = new QLabel(QStringLiteral("00:00"));
    m_countdown->hide();
    m_actionLabel = new QLabel(QStringLiteral("等待开始"));
    m_actionLabel->hide();
    m_subtitle = new QLabel();
    m_subtitle->hide();
    m_instruction = new QLabel(
        QStringLiteral("点击下方「进入评估」后，将切换到摄像头界面并开始动作采集。"));
    m_instruction->setStyleSheet("font-size:13px; color:#505050; border:none; padding:2px;");
    m_instruction->setWordWrap(true);
    lay->addWidget(m_instruction);

    m_resultPanel = new QWidget(content);
    m_resultPanel->setMinimumHeight(200);
    QHBoxLayout *resultLay = new QHBoxLayout(m_resultPanel);
    resultLay->setContentsMargins(0, 4, 0, 0);
    resultLay->setSpacing(10);

    m_radar = new RadarChart(m_resultPanel);
    m_radar->setDimensions({QStringLiteral("抬举幅度"), QStringLiteral("运动平滑度"), QStringLiteral("震颤程度"), QStringLiteral("双侧对称性"), QStringLiteral("运动速度"), QStringLiteral("运动耐力")});
    m_radar->setMinimumSize(220, 220);
    m_radar->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Preferred);
    resultLay->addWidget(m_radar, 1, Qt::AlignVCenter);

    QVBoxLayout *scoreLay = new QVBoxLayout();
    m_scoreLabel = new QLabel("--", m_resultPanel);
    m_scoreLabel->setStyleSheet("font-size:36px; font-weight:bold; color:#1A5276; border:none;");
    m_scoreLabel->setAlignment(Qt::AlignCenter);
    scoreLay->addWidget(m_scoreLabel);

    m_levelLabel = new QLabel(QStringLiteral("等待评估"), m_resultPanel);
    m_levelLabel->setStyleSheet("font-size:16px; font-weight:bold; color:#606060; border:none;");
    m_levelLabel->setAlignment(Qt::AlignCenter);
    scoreLay->addWidget(m_levelLabel);

    m_adviceLabel = new QLabel(QStringLiteral("完成测评后将在这里显示康复建议"), m_resultPanel);
    m_adviceLabel->setWordWrap(true);
    m_adviceLabel->setSizePolicy(QSizePolicy::Preferred, QSizePolicy::MinimumExpanding);
    m_adviceLabel->setMinimumHeight(44);
    m_adviceLabel->setStyleSheet(
        "background:#F8FBFF; color:#333333; border:1px solid #D0DDE8; border-radius:10px;"
        "font-size:13px; line-height:140%; padding:6px 8px;");
    scoreLay->addWidget(m_adviceLabel, 1);
    resultLay->addLayout(scoreLay, 1);
    lay->addWidget(m_resultPanel);

    scroll->setWidget(content);
    introOuter->addWidget(scroll, 1);

    QHBoxLayout *introBtnRow = new QHBoxLayout();
    introBtnRow->setContentsMargins(12, 2, 12, 6);
    introBtnRow->addStretch();
    m_enterBtn = new QPushButton(QStringLiteral("进入评估"));
    m_enterBtn->setFixedHeight(52);
    m_enterBtn->setMinimumWidth(300);
    m_enterBtn->setMaximumWidth(480);
    m_enterBtn->setStyleSheet(
        "QPushButton{background:#2E86C1; color:white; border:none; border-radius:12px;"
        "font-size:17px; font-weight:bold; padding:0 24px;}"
        "QPushButton:pressed{background:#1A5276;}"
        "QPushButton:disabled{background:#A0A0A0;}");
    connect(m_enterBtn, &QPushButton::clicked, this, &AssessmentPage::onEnterSession);
    introBtnRow->addWidget(m_enterBtn);
    introBtnRow->addStretch();
    introOuter->addLayout(introBtnRow);

    m_startBtn = m_enterBtn;

    // —— 评估会话页：摄像头 + 实时引导 ——
    m_sessionPage = new QWidget();
    QVBoxLayout *sessionLay = new QVBoxLayout(m_sessionPage);
    sessionLay->setContentsMargins(12, 8, 12, 8);
    sessionLay->setSpacing(6);

    m_visionPreview = new VisionPreviewWidget(m_sessionPage);
    m_visionPreview->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
    sessionLay->addWidget(m_visionPreview, 0);
    m_sessionProgress = m_visionPreview->topProgressBar();
    m_sessionProgress->setRange(0, m_collectSeconds);
    m_sessionProgress->setValue(0);
    m_sessionCountdown = m_visionPreview->topCountdownLabel();
    m_sessionCountdown->setText(QStringLiteral("00:00"));
    m_visionPreview->setTopProgressVisible(true);
    m_visionPreview->setTopCountdownVisible(true);

    m_sessionLowerScroll = new QScrollArea(m_sessionPage);
    m_sessionLowerScroll->setWidgetResizable(true);
    m_sessionLowerScroll->setFrameShape(QFrame::NoFrame);
    m_sessionLowerScroll->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    m_sessionLowerScroll->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);

    m_sessionLowerBody = new QWidget(m_sessionLowerScroll);
    QVBoxLayout *lowerLay = new QVBoxLayout(m_sessionLowerBody);
    lowerLay->setContentsMargins(0, 12, 0, 0);
    lowerLay->setSpacing(8);

    m_sessionVoiceHint = new QLabel(QStringLiteral("请听语音并看大字字幕"), m_sessionLowerBody);
    m_sessionVoiceHint->setWordWrap(true);
    m_sessionVoiceHint->setAlignment(Qt::AlignLeft | Qt::AlignVCenter);
    m_sessionVoiceHint->setSizePolicy(QSizePolicy::Preferred, QSizePolicy::Minimum);
    lowerLay->addWidget(m_sessionVoiceHint);

    m_sessionActionLabel = new QLabel(QStringLiteral("等待开始"), m_sessionLowerBody);
    m_sessionActionLabel->setWordWrap(true);
    m_sessionActionLabel->setSizePolicy(QSizePolicy::Preferred, QSizePolicy::Minimum);
    lowerLay->addWidget(m_sessionActionLabel);

    m_sessionSubtitleScroll = new QScrollArea(m_sessionLowerBody);
    m_sessionSubtitleScroll->setWidgetResizable(true);
    m_sessionSubtitleScroll->setFrameShape(QFrame::NoFrame);
    m_sessionSubtitleScroll->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    m_sessionSubtitleScroll->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);
    m_sessionSubtitleScroll->setMinimumHeight(96);

    m_sessionSubtitle = new QLabel(
        QStringLiteral("评估进行中，请按语音与字幕完成动作。"));
    m_sessionSubtitle->setWordWrap(true);
    m_sessionSubtitle->setAlignment(Qt::AlignLeft | Qt::AlignTop);
    m_sessionSubtitle->setSizePolicy(QSizePolicy::Preferred, QSizePolicy::Minimum);
    m_sessionSubtitle->setStyleSheet(
        "font-size:20px; font-weight:bold; color:#0B5345; border:none; padding:10px 12px;"
        "background:#E8F8F5; border-radius:12px; line-height:150%;");
    m_sessionSubtitleScroll->setWidget(m_sessionSubtitle);
    lowerLay->addWidget(m_sessionSubtitleScroll, 1);

    m_sessionLowerScroll->setWidget(m_sessionLowerBody);
    sessionLay->addWidget(m_sessionLowerScroll, 1);

    m_pageStack->addWidget(m_introPage);
    m_pageStack->addWidget(m_sessionPage);
    m_pageStack->setCurrentWidget(m_introPage);

    applyFontStyles();
}

void AssessmentPage::applyFontStyles(const QString &scoreColor)
{
    const FontScale *fs = FontScale::instance();
    const bool large = fs->largeMode();
    const QString sc = scoreColor.isEmpty() ? QStringLiteral("#1A5276") : scoreColor;
    const QString levelColor = scoreColor.isEmpty() ? QStringLiteral("#606060") : scoreColor;

    m_title->setStyleSheet(
        QStringLiteral("font-size:%1px; font-weight:bold; color:#1A5276; border:none;")
            .arg(fs->px(20)));
    m_voiceHint->setStyleSheet(
        QStringLiteral(
            "font-size:%1px; font-weight:bold; color:#1A5276; background:#F8FBFF; border:1px solid #D0DDE8;"
            "border-radius:8px; padding:%2px %3px; line-height:160%;")
            .arg(fs->px(large ? 16 : 14))
            .arg(large ? 10 : 8)
            .arg(large ? 12 : 10));
    m_voiceHint->setMaximumHeight(QWIDGETSIZE_MAX);
    m_actionList->setStyleSheet(
        QStringLiteral(
            "font-size:%1px; color:#4A4A4A; background:#FFFFFF; border:1px solid #E0E8EF;"
            "border-radius:8px; padding:%2px %3px; line-height:150%;")
            .arg(fs->px(13))
            .arg(large ? 10 : 6)
            .arg(large ? 12 : 10));
    m_actionList->setMaximumHeight(QWIDGETSIZE_MAX);
    m_instruction->setStyleSheet(
        QStringLiteral("font-size:%1px; color:#505050; border:none; padding:2px;")
            .arg(fs->px(13)));
    m_scoreLabel->setStyleSheet(
        QStringLiteral("font-size:%1px; font-weight:bold; color:%2; border:none;")
            .arg(fs->px(36))
            .arg(sc));
    m_levelLabel->setStyleSheet(
        QStringLiteral("font-size:%1px; font-weight:bold; color:%2; border:none;")
            .arg(fs->px(16))
            .arg(levelColor));
    m_adviceLabel->setStyleSheet(
        QStringLiteral(
            "background:#F8FBFF; color:#333333; border:1px solid #D0DDE8; border-radius:10px;"
            "font-size:%1px; line-height:150%; padding:%2px %3px;")
            .arg(fs->px(13))
            .arg(large ? 10 : 6)
            .arg(large ? 10 : 8));
    m_adviceLabel->setMinimumHeight(large ? 96 : 44);
    if (m_resultPanel) {
        m_resultPanel->setMinimumHeight(large ? 340 : 200);
    }
    if (m_enterBtn) {
        m_enterBtn->setFixedHeight(fs->largeMode() ? 62 : 52);
        m_enterBtn->setStyleSheet(
            QStringLiteral(
                "QPushButton{background:#2E86C1; color:white; border:none; border-radius:12px;"
                "font-size:%1px; font-weight:bold; padding:0 24px;}"
                "QPushButton:pressed{background:#1A5276;}"
                "QPushButton:disabled{background:#A0A0A0;}")
                .arg(fs->px(17)));
    }
    m_sessionVoiceHint->setStyleSheet(
        QStringLiteral(
            "font-size:%1px; font-weight:bold; color:#0B5345; background:#F8FBFF;"
            "border:1px solid #BFD7EA; border-radius:10px; padding:%2px %3px;")
            .arg(fs->px(14))
            .arg(large ? 8 : 6)
            .arg(large ? 12 : 10));
    const int progressH = large ? 32 : 26;
    const int progressFont = fs->px(13);
    if (m_sessionProgress) {
        m_sessionProgress->setFixedHeight(progressH);
        m_sessionProgress->setStyleSheet(
            QStringLiteral(
                "QProgressBar{border:1px solid rgba(255,255,255,90); border-radius:8px;"
                "background:rgba(0,0,0,150); min-height:%1px; max-height:%1px;"
                "text-align:center; font-size:%2px; font-weight:800; color:#FFFFFF; padding:1px 6px;}"
                "QProgressBar::chunk{background:#2E86C1; border-radius:7px;}")
                .arg(progressH)
                .arg(progressFont));
    }
    if (m_visionPreview) {
        m_visionPreview->refreshOverlays();
    }
    if (m_sessionCountdown) {
        m_sessionCountdown->setStyleSheet(
            QStringLiteral(
                "font-size:%1px; font-weight:900; color:#FFFFFF; background:#1A5276;"
                "border:1px solid rgba(255,255,255,90); border-radius:8px; padding:%2px %3px;")
                .arg(fs->px(large ? 16 : 14))
                .arg(large ? 4 : 2)
                .arg(large ? 10 : 8));
        m_sessionCountdown->setMinimumWidth(large ? 88 : 72);
        m_sessionCountdown->setFixedHeight(progressH);
    }
    m_sessionActionLabel->setStyleSheet(
        QStringLiteral(
            "font-size:%1px; font-weight:bold; color:#1B2631; background:#FFFFFF;"
            "border:1px solid #D0DDE8; border-radius:8px; padding:%2px %3px;")
            .arg(fs->px(15))
            .arg(large ? 6 : 4)
            .arg(large ? 10 : 8));
    m_sessionSubtitle->setStyleSheet(
        QStringLiteral(
            "font-size:%1px; font-weight:bold; color:#0B5345; border:none; padding:%2px %3px;"
            "background:#E8F8F5; border-radius:12px; line-height:160%;")
            .arg(fs->px(20))
            .arg(large ? 12 : 10)
            .arg(large ? 14 : 12));
    m_sessionSubtitle->setMinimumHeight(0);
    refreshSessionSubtitleLayout();
    if (m_sessionSubtitleScroll) {
        m_sessionSubtitleScroll->setMinimumHeight(large ? 120 : 88);
    }
    refreshSessionChrome(m_lastPhase);
    if (m_radar) {
        const int side = large ? 300 : 220;
        m_radar->setMinimumSize(side, side);
        m_radar->updateGeometry();
        m_radar->update();
    }
}

void AssessmentPage::applyFontScale()
{
    QString scoreColor;
    if (m_hasStoredResult && !m_result.levelColor.isEmpty()) {
        scoreColor = m_result.levelColor;
    }
    applyFontStyles(scoreColor);
    if (m_hasStoredResult) {
        showResultOnPage(m_result, false);
    }
}

void AssessmentPage::onEnterSession()
{
    showSessionPage();
    if (m_visionPreview) {
        m_visionPreview->setBottomBarText(
            QStringLiteral("📷 检测中 ｜ 评估时将检测抬举角度与动作质量"));
    }
    beginAssessmentSession();
}

void AssessmentPage::refreshSessionChrome(const QString &phase)
{
    const bool precheck = (phase == QStringLiteral("precheck"));
    // 预检：环境状态（逆光等）已在摄像头画面底部条 + 大字字幕中展示，隐藏外部重复条避免遮挡画面
    if (m_sessionVoiceHint) {
        m_sessionVoiceHint->setVisible(!precheck);
    }
    if (m_sessionActionLabel) {
        m_sessionActionLabel->setVisible(!precheck);
    }
    if (m_visionPreview) {
        m_visionPreview->setTopProgressVisible(!precheck);
        m_visionPreview->setTopCountdownVisible(!precheck);
    }
}

void AssessmentPage::refreshSessionSubtitleLayout()
{
    if (!m_sessionSubtitle || !m_sessionSubtitleScroll) {
        return;
    }
    const int viewportW = m_sessionSubtitleScroll->viewport()->width();
    if (viewportW > 40) {
        m_sessionSubtitle->setMinimumWidth(viewportW);
        m_sessionSubtitle->setMaximumWidth(viewportW);
    }
    m_sessionSubtitle->adjustSize();
    const int contentH = m_sessionSubtitle->sizeHint().height();
    const int viewportH = m_sessionSubtitleScroll->viewport()->height();
    if (contentH > viewportH) {
        m_sessionSubtitleScroll->setVerticalScrollBarPolicy(Qt::ScrollBarAsNeeded);
    }
    m_sessionSubtitleScroll->updateGeometry();
}

void AssessmentPage::updateVisionPreviewHeight()
{
    if (!m_visionPreview || !m_sessionPage) {
        return;
    }
    QScreen *screen = QGuiApplication::primaryScreen();
    const int sh = screen ? screen->availableGeometry().height() : 720;
    const int fullH = ElderUx::visionPreviewHeight(m_sessionPage->width(), sh);
    const bool large = FontScale::instance()->largeMode();

    // 摄像头默认按宽度/屏幕比例计算（约 220–380px），不再为字幕强行压到 140px
    int minH = fullH;
    int maxH = fullH;
    if (m_engineMode && m_collectActive) {
        maxH = qMin(fullH + (large ? 72 : 48), int(sh * 0.44));
    }

    m_visionPreview->setMinimumHeight(minH);
    m_visionPreview->setMaximumHeight(maxH);
    m_visionPreview->refreshOverlays();
    refreshSessionSubtitleLayout();
}

void AssessmentPage::resizeEvent(QResizeEvent *event)
{
    QWidget::resizeEvent(event);
    updateVisionPreviewHeight();
}

void AssessmentPage::refresh()
{
    if (m_engine && m_engine->isConnected()) {
        m_engine->sendCommand(QStringLiteral("request_assessment_result"));
    }
    if (m_hasStoredResult) {
        showResultOnPage(m_result, false);
    } else {
        resetReadyState();
    }
    requestAssessmentPlan();
}

void AssessmentPage::loadStoredAssessment()
{
    ScoreResult stored;
    if (DataStorage::loadLatestAssessment(&stored)) {
        m_result = stored;
        m_hasStoredResult = true;
        showResultOnPage(m_result, false);
    } else {
        resetReadyState();
    }
}

void AssessmentPage::resetReadyState()
{
    showIntroPage();
    m_actionList->setMaximumHeight(QWIDGETSIZE_MAX);
    m_radar->clear();
    m_collectActive = false;
    m_phaseElapsed = 0;
    m_sessionElapsed = 0;
    m_progress->setRange(0, m_collectSeconds);
    m_progress->setValue(0);
    m_instruction->setText(
        QStringLiteral("点击下方「进入评估」后，将切换到摄像头界面并开始动作采集。"));
    m_scoreLabel->setText("--");
    m_levelLabel->setText(QStringLiteral("等待评估"));
    applyFontStyles();
    m_adviceLabel->setText(QStringLiteral("完成测评后将在这里显示康复建议"));
    if (m_visionPreview) {
        m_visionPreview->clearPreview();
        m_visionPreview->setBottomBarText(QString());
        m_visionPreview->setTopRightText(QString());
    }
    m_visionFusionNote.clear();
    if (m_enterBtn) {
        m_enterBtn->setEnabled(true);
        m_enterBtn->setText(QStringLiteral("进入评估"));
    }
}

void AssessmentPage::showResultOnPage(const ScoreResult &result, bool finishedState)
{
    m_radar->setValues(result.dims);
    m_actionList->setMaximumHeight(
        FontScale::instance()->largeMode() ? QWIDGETSIZE_MAX : 72);
    m_scoreLabel->setText(QString::number(qBound(0, result.compositeScore, 100)) + QStringLiteral("分"));
    const QString color = result.levelColor.isEmpty()
            ? ScoreEngine::levelColor(ScoreEngine::scoreToLevel(result.compositeScore))
            : result.levelColor;
    const QString levelName = result.levelName.isEmpty()
            ? ScoreEngine::levelName(ScoreEngine::scoreToLevel(result.compositeScore))
            : result.levelName;
    const QString advice = result.advice.isEmpty()
            ? ScoreEngine::randomAdviceForScore(result.compositeScore)
            : result.advice;

    m_levelLabel->setText(levelName);
    applyFontStyles(color);
    m_adviceLabel->setText(
        m_visionFusionNote.isEmpty()
            ? QStringLiteral("康复建议：%1").arg(advice)
            : QStringLiteral("%1\n\n康复建议：%2").arg(m_visionFusionNote, advice));
    if (m_enterBtn) {
        m_enterBtn->setEnabled(true);
        m_enterBtn->setText(QStringLiteral("重新评估"));
    }

    if (finishedState) {
        m_instruction->setText(QStringLiteral("评估完成！请查看右侧评分结果。"));
    } else {
        m_instruction->setText(QStringLiteral("已读取上一次评估结果。点击「重新评估」进入摄像头界面。"));
    }
    m_progress->setValue(finishedState ? m_collectSeconds : 0);
}

void AssessmentPage::onStartAssessment()
{
    onEnterSession();
}

void AssessmentPage::onTick()
{
    if (!m_engineMode) {
        return;
    }

    if (m_collectActive && m_collectSeconds > 0) {
        ++m_phaseElapsed;
        const int progressVal = qMin(m_collectSeconds, m_phaseElapsed);
        const int remain = qMax(0, m_collectSeconds - m_phaseElapsed);
        m_sessionProgress->setValue(progressVal);
        m_sessionCountdown->setText(formatCountdown(remain));
        if (m_visionPreview) {
            m_visionPreview->refreshOverlays();
        }
        if (m_phaseElapsed >= m_collectSeconds) {
            m_collectActive = false;
        }
    }

    ++m_sessionElapsed;
    if (m_sessionElapsed >= m_totalSeconds + 90) {
        m_timer->stop();
        m_engineMode = false;
        m_collectActive = false;
        showIntroPage();
        if (m_enterBtn) {
            m_enterBtn->setEnabled(true);
            m_enterBtn->setText(QStringLiteral("进入评估"));
        }
        m_instruction->setText(QStringLiteral("评估超时，请检查后端日志或稍后重试。"));
    }
}

void AssessmentPage::onScoreReady(const ScoreResult &result)
{
    applyAssessmentResult(result, true);
}

void AssessmentPage::applyAssessmentResult(const ScoreResult &result, bool emitCompletion)
{
    m_result = result;
    if (!m_result.timestamp.isValid()) {
        m_result.timestamp = QDateTime::currentDateTime();
    }
    m_hasStoredResult = true;
    DataStorage::saveLatestAssessment(m_result);
    showResultOnPage(m_result, emitCompletion);
    if (emitCompletion) {
        emit assessmentCompleted(m_result);
    }
}
