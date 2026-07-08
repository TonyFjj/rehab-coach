#ifndef SETTINGSPAGE_H
#define SETTINGSPAGE_H

#include <QWidget>
#include <QLabel>
#include <QPushButton>
#include <QSlider>
#include <QLineEdit>
#include <QGroupBox>
#include <QTimer>

class EngineBridge;

class SettingsPage : public QWidget
{
    Q_OBJECT
public:
    explicit SettingsPage(QWidget *parent = nullptr);
    void refresh();
    void setEngineBridge(EngineBridge *engine);
    void applyFontScale();

signals:
    void accessibilityChanged();

private slots:
    void onVolumeChanged(int value);
    void onSpeedChanged(int value);
    void onEngineConnectionChanged(bool connected);
    void onSystemStatusReceived(const QJsonObject &payload);
    void pushAudioSettings();
    void onLargeTextToggled(bool checked);

private:
    void setupUI();
    void loadLocalSettings();
    void saveLocalSettings();
    void applyVolumeSlider(int percent);
    void applySpeedSlider(int sliderValue);
    void setImuLrHint(const QString &text, const QString &color);
    void applyImuLrResult(const QString &result);
    void loadImuLrResult();
    void saveImuLrResult(const QString &result);
    void updateLargeTextButton();

    EngineBridge *m_engine = nullptr;
    QTimer *m_pushTimer = nullptr;
    bool m_blockSliderSignals = false;

    QLabel *m_title;
    QLineEdit *m_nameEdit;
    QLineEdit *m_ageEdit;
    QSlider *m_volumeSlider;
    QSlider *m_speedSlider;
    QLabel *m_volumeLabel;
    QLabel *m_speedLabel;
    QLabel *m_voiceStatus;
    QPushButton *m_calibImuBtn;
    QPushButton *m_calibImuLrBtn;
    QPushButton *m_imuAssessBtn;
    QPushButton *m_calibCamBtn;
    QLabel *m_imuLrStatus;
    QLabel *m_imuStatus;
    QLabel *m_camStatus;
    QLabel *m_sysInfo;
    QPushButton *m_largeTextBtn = nullptr;

    QString m_lastLrResult;
    bool m_lrCalibrating = false;
};
#endif // SETTINGSPAGE_H
