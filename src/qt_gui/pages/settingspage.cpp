#include "settingspage.h"
#include "ipc/enginebridge.h"
#include "models/datastorage.h"
#include "utils/fontscale.h"

#include <QVBoxLayout>
#include <QHBoxLayout>
#include <QFormLayout>
#include <QJsonObject>
#include <QScrollArea>
#include <QFrame>

SettingsPage::SettingsPage(QWidget *parent) : QWidget(parent)
{
    m_pushTimer = new QTimer(this);
    m_pushTimer->setSingleShot(true);
    m_pushTimer->setInterval(250);
    connect(m_pushTimer, &QTimer::timeout, this, &SettingsPage::pushAudioSettings);
    setupUI();
    loadLocalSettings();
    loadImuLrResult();
}

void SettingsPage::setEngineBridge(EngineBridge *engine)
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
            this, &SettingsPage::onEngineConnectionChanged);
    connect(m_engine, &EngineBridge::systemStatusReceived,
            this, &SettingsPage::onSystemStatusReceived);
    onEngineConnectionChanged(m_engine->isConnected());
}

void SettingsPage::setupUI()
{
    QVBoxLayout *outer = new QVBoxLayout(this);
    outer->setContentsMargins(0, 0, 0, 0);

    QScrollArea *scroll = new QScrollArea(this);
    scroll->setWidgetResizable(true);
    scroll->setFrameShape(QFrame::NoFrame);
    scroll->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);

    QWidget *content = new QWidget();
    QVBoxLayout *lay = new QVBoxLayout(content);
    lay->setContentsMargins(24, 16, 24, 8);

    m_title = new QLabel(QStringLiteral("系统设置"));
    m_title->setStyleSheet("font-size:22px; font-weight:bold; color:#1A5276; border:none;");
    lay->addWidget(m_title);

    QGroupBox *infoGroup = new QGroupBox(QStringLiteral("患者信息"));
    infoGroup->setStyleSheet(
        "QGroupBox{font-size:15px; font-weight:bold; color:#1A5276; border:1px solid #D0DDE8;"
        "border-radius:12px; margin-top:8px; padding-top:16px;}"
        "QGroupBox::title{subcontrol-origin:margin; left:16px;}");
    QFormLayout *formLay = new QFormLayout(infoGroup);
    m_nameEdit = new QLineEdit(QStringLiteral("王爷爷"));
    m_nameEdit->setMinimumHeight(40);
    m_nameEdit->setStyleSheet("border:1px solid #D0DDE8; border-radius:8px; padding:4px 8px; font-size:14px;");
    m_ageEdit = new QLineEdit(QStringLiteral("72"));
    m_ageEdit->setMinimumHeight(40);
    m_ageEdit->setStyleSheet("border:1px solid #D0DDE8; border-radius:8px; padding:4px 8px; font-size:14px;");
    formLay->addRow(QStringLiteral("姓名:"), m_nameEdit);
    formLay->addRow(QStringLiteral("年龄:"), m_ageEdit);
    lay->addWidget(infoGroup);

    QGroupBox *voiceGroup = new QGroupBox(QStringLiteral("语音设置"));
    voiceGroup->setStyleSheet(infoGroup->styleSheet());
    QVBoxLayout *voiceLay = new QVBoxLayout(voiceGroup);

    QHBoxLayout *volLay = new QHBoxLayout();
    volLay->addWidget(new QLabel(QStringLiteral("音量:")));
    m_volumeSlider = new QSlider(Qt::Horizontal);
    m_volumeSlider->setRange(0, 100);
    m_volumeSlider->setValue(90);
    m_volumeLabel = new QLabel(QStringLiteral("90%"));
    m_volumeLabel->setFixedWidth(48);
    volLay->addWidget(m_volumeSlider);
    volLay->addWidget(m_volumeLabel);
    voiceLay->addLayout(volLay);
    connect(m_volumeSlider, &QSlider::valueChanged, this, &SettingsPage::onVolumeChanged);

    QHBoxLayout *spdLay = new QHBoxLayout();
    spdLay->addWidget(new QLabel(QStringLiteral("语速:")));
    m_speedSlider = new QSlider(Qt::Horizontal);
    m_speedSlider->setRange(50, 200);
    m_speedSlider->setValue(100);
    m_speedLabel = new QLabel(QStringLiteral("1.0x"));
    m_speedLabel->setFixedWidth(48);
    spdLay->addWidget(m_speedSlider);
    spdLay->addWidget(m_speedLabel);
    voiceLay->addLayout(spdLay);
    connect(m_speedSlider, &QSlider::valueChanged, this, &SettingsPage::onSpeedChanged);

    QHBoxLayout *largeLay = new QHBoxLayout();
    m_largeTextBtn = new QPushButton(QStringLiteral("大字模式"));
    m_largeTextBtn->setCheckable(true);
    m_largeTextBtn->setMinimumSize(132, 44);
    connect(m_largeTextBtn, &QPushButton::toggled,
            this, &SettingsPage::onLargeTextToggled);
    largeLay->addWidget(m_largeTextBtn);
    largeLay->addStretch();
    voiceLay->addLayout(largeLay);

    m_voiceStatus = new QLabel(QStringLiteral("音量/语速将在连接后端后实时生效"));
    m_voiceStatus->setWordWrap(true);
    m_voiceStatus->setStyleSheet("font-size:13px; color:#606060; border:none;");
    voiceLay->addWidget(m_voiceStatus);

    lay->addWidget(voiceGroup);

    QGroupBox *sensorGroup = new QGroupBox(QStringLiteral("传感器校准"));
    sensorGroup->setStyleSheet(infoGroup->styleSheet());
    QVBoxLayout *sensorLay = new QVBoxLayout(sensorGroup);

    QHBoxLayout *imuLay = new QHBoxLayout();
    m_calibImuBtn = new QPushButton(QStringLiteral("IMU校准"));
    m_calibImuBtn->setMinimumSize(120, 44);
    m_calibImuBtn->setStyleSheet(
        "QPushButton{background:#2E86C1; color:white; border:none; border-radius:10px; font-size:14px;}"
        "QPushButton:pressed{background:#1A5276;}");
    connect(m_calibImuBtn, &QPushButton::clicked, this, [this]() {
        if (!m_engine || !m_engine->isConnected()) {
            m_imuStatus->setText(QStringLiteral("状态: 后端未连接"));
            m_imuStatus->setStyleSheet("font-size:13px; color:#E74C3C; border:none;");
            return;
        }
        m_imuStatus->setText(QStringLiteral("状态: 校准中，请保持静止…"));
        m_imuStatus->setStyleSheet("font-size:13px; color:#F39C12; border:none;");
        m_engine->sendCommand(QStringLiteral("start_imu_calibration"));
        QTimer::singleShot(3500, this, [this]() {
            if (m_engine && m_engine->isConnected()) {
                m_engine->sendCommand(QStringLiteral("finish_imu_calibration"));
            }
        });
    });
    m_imuAssessBtn = new QPushButton(QStringLiteral("评估（同评估页）"));
    m_imuAssessBtn->setMinimumSize(120, 44);
    m_imuAssessBtn->setStyleSheet(m_calibImuBtn->styleSheet());
    connect(m_imuAssessBtn, &QPushButton::clicked, this, [this]() {
        if (!m_engine || !m_engine->isConnected()) {
            return;
        }
        m_imuStatus->setText(QStringLiteral("状态: 评估进行中（30秒连续动作）…"));
        m_imuStatus->setStyleSheet("font-size:13px; color:#F39C12; border:none;");
        QJsonObject extra;
        extra.insert(QStringLiteral("force"), true);
        m_engine->sendCommand(QStringLiteral("start_assessment"), extra);
    });
    m_calibImuLrBtn = new QPushButton(QStringLiteral("IMU左右手校准"));
    m_calibImuLrBtn->setMinimumSize(140, 44);
    m_calibImuLrBtn->setStyleSheet(m_calibImuBtn->styleSheet());
    connect(m_calibImuLrBtn, &QPushButton::clicked, this, [this]() {
        if (!m_engine || !m_engine->isConnected()) {
            setImuLrHint(QStringLiteral("左右手: 后端未连接"), QStringLiteral("#E74C3C"));
            return;
        }
        m_lrCalibrating = true;
        setImuLrHint(QStringLiteral("左右手: 校准启动中…"), QStringLiteral("#F39C12"));
        m_calibImuLrBtn->setEnabled(false);
        m_engine->sendCommand(QStringLiteral("start_imu_lr_calibration"));
        QTimer::singleShot(12000, this, [this]() {
            if (m_calibImuLrBtn) {
                m_calibImuLrBtn->setEnabled(true);
            }
        });
    });
    m_imuLrStatus = new QLabel(QStringLiteral("左右手: 未校准"));
    m_imuLrStatus->setMinimumWidth(160);
    m_imuLrStatus->setWordWrap(true);
    m_imuLrStatus->setStyleSheet("font-size:13px; color:#909090; border:none;");
    m_imuStatus = new QLabel(QStringLiteral("IMU: 未连接"));
    m_imuStatus->setStyleSheet("font-size:13px; color:#E74C3C; border:none;");
    imuLay->addWidget(m_calibImuBtn);
    imuLay->addWidget(m_calibImuLrBtn);
    imuLay->addWidget(m_imuLrStatus);
    imuLay->addWidget(m_imuAssessBtn);
    imuLay->addWidget(m_imuStatus);
    imuLay->addStretch();
    sensorLay->addLayout(imuLay);

    QHBoxLayout *camLay = new QHBoxLayout();
    m_calibCamBtn = new QPushButton(QStringLiteral("双目标定"));
    m_calibCamBtn->setMinimumSize(120, 44);
    m_calibCamBtn->setStyleSheet(m_calibImuBtn->styleSheet());
    m_camStatus = new QLabel(QStringLiteral("状态: 未连接"));
    m_camStatus->setStyleSheet("font-size:13px; color:#E74C3C; border:none;");
    camLay->addWidget(m_calibCamBtn);
    camLay->addWidget(m_camStatus);
    camLay->addStretch();
    sensorLay->addLayout(camLay);

    lay->addWidget(sensorGroup);

    m_sysInfo = new QLabel(QStringLiteral("设备: ELF2 (RK3588) | NPU: 6TOPS | 内存: 8GB | 版本: v1.0.0"));
    m_sysInfo->setWordWrap(true);
    m_sysInfo->setStyleSheet("font-size:12px; color:#A0A0A0; border:none; padding:8px;");
    lay->addWidget(m_sysInfo);

    scroll->setWidget(content);
    outer->addWidget(scroll);

    updateLargeTextButton();
}

void SettingsPage::loadLocalSettings()
{
    QJsonObject root;
    if (!DataStorage::loadAppSettings(&root)) {
        return;
    }
    m_blockSliderSignals = true;
    if (root.contains(QStringLiteral("volume"))) {
        applyVolumeSlider(root.value(QStringLiteral("volume")).toInt(90));
    }
    if (root.contains(QStringLiteral("speed"))) {
        applySpeedSlider(root.value(QStringLiteral("speed")).toInt(100));
    }
    if (m_largeTextBtn) {
        m_largeTextBtn->blockSignals(true);
        m_largeTextBtn->setChecked(
            root.value(QStringLiteral("largeTextMode")).toBool(false));
        m_largeTextBtn->blockSignals(false);
        updateLargeTextButton();
    }
    m_blockSliderSignals = false;
}

void SettingsPage::saveLocalSettings()
{
    QJsonObject root;
    DataStorage::loadAppSettings(&root);
    root.insert(QStringLiteral("volume"), m_volumeSlider->value());
    root.insert(QStringLiteral("speed"), m_speedSlider->value());
    if (m_largeTextBtn) {
        root.insert(QStringLiteral("largeTextMode"), m_largeTextBtn->isChecked());
    }
    DataStorage::saveAppSettings(root);
}

void SettingsPage::applyVolumeSlider(int percent)
{
    const int v = qBound(0, percent, 100);
    m_volumeSlider->setValue(v);
    m_volumeLabel->setText(QString::number(v) + QStringLiteral("%"));
}

void SettingsPage::applySpeedSlider(int sliderValue)
{
    const int v = qBound(50, sliderValue, 200);
    m_speedSlider->setValue(v);
    m_speedLabel->setText(QString::number(v / 100.0, 'f', 1) + QStringLiteral("x"));
}

void SettingsPage::onVolumeChanged(int value)
{
    applyVolumeSlider(value);
    saveLocalSettings();
    if (!m_blockSliderSignals) {
        m_pushTimer->start();
    }
}

void SettingsPage::onSpeedChanged(int value)
{
    applySpeedSlider(value);
    saveLocalSettings();
    if (!m_blockSliderSignals) {
        m_pushTimer->start();
    }
}

void SettingsPage::pushAudioSettings()
{
    if (!m_engine || !m_engine->isConnected()) {
        m_voiceStatus->setText(QStringLiteral("后端未连接，设置已保存，连接后将自动同步"));
        m_voiceStatus->setStyleSheet("font-size:13px; color:#E67E22; border:none;");
        return;
    }

    QJsonObject extra;
    extra.insert(QStringLiteral("volume"), m_volumeSlider->value());
    extra.insert(QStringLiteral("speed"), m_speedSlider->value());
    m_engine->sendCommand(QStringLiteral("set_volume"), extra);
    m_engine->sendCommand(QStringLiteral("set_speed"), extra);

    m_voiceStatus->setText(
        QStringLiteral("已同步到后端 TTS：音量 %1%，语速 %2x")
            .arg(m_volumeSlider->value())
            .arg(m_speedSlider->value() / 100.0, 0, 'f', 1));
    m_voiceStatus->setStyleSheet("font-size:13px; color:#27AE60; border:none;");
}

void SettingsPage::onEngineConnectionChanged(bool connected)
{
    if (!connected) {
        m_voiceStatus->setText(QStringLiteral("后端未连接，请先启动 rehab-coach-rknn"));
        m_voiceStatus->setStyleSheet("font-size:13px; color:#E74C3C; border:none;");
        return;
    }
    if (m_engine) {
        m_engine->sendCommand(QStringLiteral("request_status"));
    }
    pushAudioSettings();
}

void SettingsPage::onSystemStatusReceived(const QJsonObject &payload)
{
    if (payload.contains(QStringLiteral("tts_volume"))
        || payload.contains(QStringLiteral("tts_rate"))) {
        m_blockSliderSignals = true;
        if (payload.contains(QStringLiteral("tts_volume"))) {
            const int percent = qRound(
                payload.value(QStringLiteral("tts_volume")).toDouble(0.9) * 100.0);
            applyVolumeSlider(percent);
        }
        if (payload.contains(QStringLiteral("tts_rate"))) {
            const int rate = payload.value(QStringLiteral("tts_rate")).toInt(160);
            const int slider = qBound(50, qRound(rate * 100.0 / 160.0), 200);
            applySpeedSlider(slider);
        }
        m_blockSliderSignals = false;
        saveLocalSettings();
    }

    const QJsonObject imu = payload.value(QStringLiteral("imu")).toObject();
    if (imu.isEmpty()) {
        return;
    }
    if (imu.value(QStringLiteral("lr_calibrating")).toBool()) {
        m_lrCalibrating = true;
        const QString phase = imu.value(QStringLiteral("lr_phase")).toString();
        if (phase == QStringLiteral("capturing")) {
            setImuLrHint(QStringLiteral("左右手: 采集中，请保持抬手"), QStringLiteral("#F39C12"));
        } else if (phase == QStringLiteral("baseline")) {
            setImuLrHint(QStringLiteral("左右手: 基线采集，双手下垂"), QStringLiteral("#F39C12"));
        } else if (phase == QStringLiteral("prompt")) {
            setImuLrHint(QStringLiteral("左右手: 请听语音后抬左手"), QStringLiteral("#F39C12"));
        } else {
            setImuLrHint(QStringLiteral("左右手: 校准中…"), QStringLiteral("#F39C12"));
        }
    } else if (imu.contains(QStringLiteral("lr_result"))) {
        m_lrCalibrating = false;
        if (m_calibImuLrBtn) {
            m_calibImuLrBtn->setEnabled(true);
        }
        applyImuLrResult(imu.value(QStringLiteral("lr_result")).toString());
    }

    const bool left = imu.value(QStringLiteral("left_online")).toBool();
    const bool right = imu.value(QStringLiteral("right_online")).toBool();
    const QString mode = imu.value(QStringLiteral("mode")).toString();
    if (imu.value(QStringLiteral("calibrating")).toBool()) {
        m_imuStatus->setText(QStringLiteral("IMU: 零漂校准中，请保持静止…"));
        m_imuStatus->setStyleSheet("font-size:13px; color:#F39C12; border:none;");
        return;
    }
    if (left && right) {
        const QJsonValue portsVal = imu.value(QStringLiteral("ports"));
        QString portHint;
        if (portsVal.isObject()) {
            const QJsonObject ports = portsVal.toObject();
            const QString lp = ports.value(QStringLiteral("left")).toString();
            const QString rp = ports.value(QStringLiteral("right")).toString();
            if (!lp.isEmpty() && !rp.isEmpty()) {
                const auto shortId = [](const QString &path) -> QString {
                    const int dash = path.lastIndexOf(QLatin1Char('-'));
                    if (dash >= 0 && dash + 4 < path.size()) {
                        return path.mid(dash + 1, 4);
                    }
                    const int slash = path.lastIndexOf(QLatin1Char('/'));
                    return slash >= 0 ? path.mid(slash + 1) : path;
                };
                portHint = QStringLiteral(" (%1/%2)")
                               .arg(shortId(lp), shortId(rp));
            }
        }
        m_imuStatus->setText(
            QStringLiteral("IMU: 左右已连接%1").arg(portHint));
        m_imuStatus->setStyleSheet("font-size:13px; color:#27AE60; border:none;");
    } else if (left || right) {
        m_imuStatus->setText(
            QStringLiteral("IMU: 仅%1侧在线")
                .arg(left ? QStringLiteral("左") : QStringLiteral("右")));
        m_imuStatus->setStyleSheet("font-size:13px; color:#F39C12; border:none;");
    } else {
        m_imuStatus->setText(QStringLiteral("IMU: 未检测到数据 (%1)").arg(mode));
        m_imuStatus->setStyleSheet("font-size:13px; color:#E74C3C; border:none;");
    }
}

void SettingsPage::setImuLrHint(const QString &text, const QString &color)
{
    if (!m_imuLrStatus) {
        return;
    }
    m_imuLrStatus->setText(text);
    m_imuLrStatus->setStyleSheet(
        QStringLiteral("font-size:13px; color:%1; border:none;").arg(color));
}

void SettingsPage::applyImuLrResult(const QString &result)
{
    m_lastLrResult = result;
    saveImuLrResult(result);

    if (result == QStringLiteral("ok")) {
        setImuLrHint(QStringLiteral("左右手: 正常"), QStringLiteral("#27AE60"));
    } else if (result == QStringLiteral("swapped")) {
        setImuLrHint(QStringLiteral("左右手: 已交换"), QStringLiteral("#2980B9"));
    } else if (result == QStringLiteral("inconclusive")) {
        setImuLrHint(QStringLiteral("左右手: 动作不明显，请重试"), QStringLiteral("#E67E22"));
    } else if (result == QStringLiteral("no_data")) {
        setImuLrHint(QStringLiteral("左右手: 未收到数据"), QStringLiteral("#E74C3C"));
    } else if (result == QStringLiteral("error")) {
        setImuLrHint(QStringLiteral("左右手: 校准异常"), QStringLiteral("#E74C3C"));
    } else {
        setImuLrHint(QStringLiteral("左右手: 未知结果"), QStringLiteral("#E67E22"));
    }
}

void SettingsPage::loadImuLrResult()
{
    QJsonObject root;
    if (!DataStorage::loadAppSettings(&root)) {
        return;
    }
    const QString result = root.value(QStringLiteral("imu_lr_result")).toString();
    if (result.isEmpty()) {
        setImuLrHint(QStringLiteral("左右手: 未校准"), QStringLiteral("#909090"));
        return;
    }
    applyImuLrResult(result);
}

void SettingsPage::saveImuLrResult(const QString &result)
{
    QJsonObject root;
    DataStorage::loadAppSettings(&root);
    root.insert(QStringLiteral("imu_lr_result"), result);
    DataStorage::saveAppSettings(root);
}

void SettingsPage::refresh()
{
    loadLocalSettings();
    if (!m_lrCalibrating && m_lastLrResult.isEmpty()) {
        loadImuLrResult();
    }
    if (m_engine && m_engine->isConnected()) {
        m_engine->sendCommand(QStringLiteral("request_status"));
    }
}

void SettingsPage::updateLargeTextButton()
{
    if (!m_largeTextBtn) {
        return;
    }
    const FontScale *fs = FontScale::instance();
    const bool on = m_largeTextBtn->isChecked();
    const int btnH = fs->largeMode() ? 52 : 44;
    m_largeTextBtn->setMinimumSize(on ? 156 : 132, btnH);
    m_largeTextBtn->setText(on
        ? QStringLiteral("大字模式：开")
        : QStringLiteral("大字模式：关"));
    const QString bg = on ? QStringLiteral("#27AE60") : QStringLiteral("#2E86C1");
    m_largeTextBtn->setStyleSheet(fs->actionButtonStyle(bg, 14));
}

void SettingsPage::onLargeTextToggled(bool checked)
{
    FontScale::instance()->setLargeMode(checked);
    saveLocalSettings();
    updateLargeTextButton();
    applyFontScale();
    emit accessibilityChanged();
}

void SettingsPage::applyFontScale()
{
    const FontScale *fs = FontScale::instance();
    m_title->setStyleSheet(
        QStringLiteral("font-size:%1px; font-weight:bold; color:#1A5276; border:none;")
            .arg(fs->px(22)));
    updateLargeTextButton();

    const int btnH = fs->largeMode() ? 52 : 44;
    const QString calibStyle = fs->actionButtonStyle(QStringLiteral("#2E86C1"), 14);
    if (m_calibImuBtn) {
        m_calibImuBtn->setMinimumSize(120, btnH);
        m_calibImuBtn->setStyleSheet(calibStyle);
    }
    if (m_calibImuLrBtn) {
        m_calibImuLrBtn->setMinimumSize(140, btnH);
        m_calibImuLrBtn->setStyleSheet(calibStyle);
    }
    if (m_imuAssessBtn) {
        m_imuAssessBtn->setMinimumSize(120, btnH);
        m_imuAssessBtn->setStyleSheet(calibStyle);
    }
    if (m_calibCamBtn) {
        m_calibCamBtn->setMinimumSize(120, btnH);
        m_calibCamBtn->setStyleSheet(calibStyle);
    }

    m_voiceStatus->setStyleSheet(
        QStringLiteral("font-size:%1px; color:#606060; border:none;")
            .arg(fs->px(13)));
    m_imuStatus->setStyleSheet(
        QStringLiteral("font-size:%1px; color:#E74C3C; border:none;")
            .arg(fs->px(13)));
    m_imuLrStatus->setStyleSheet(
        QStringLiteral("font-size:%1px; color:#909090; border:none;")
            .arg(fs->px(13)));
    m_camStatus->setStyleSheet(
        QStringLiteral("font-size:%1px; color:#E74C3C; border:none;")
            .arg(fs->px(13)));
    m_sysInfo->setStyleSheet(
        QStringLiteral("font-size:%1px; color:#A0A0A0; border:none; padding:8px;")
            .arg(fs->px(12)));
    m_nameEdit->setMinimumHeight(fs->largeMode() ? 48 : 40);
    m_ageEdit->setMinimumHeight(fs->largeMode() ? 48 : 40);
    m_nameEdit->setStyleSheet(
        QStringLiteral("border:1px solid #D0DDE8; border-radius:8px; padding:4px 8px; font-size:%1px;")
            .arg(fs->px(14)));
    m_ageEdit->setStyleSheet(m_nameEdit->styleSheet());
}
