#ifndef ARCGAUGE_H
#define ARCGAUGE_H

#include <QWidget>
#include <QColor>

class ArcGauge : public QWidget
{
    Q_OBJECT
    Q_PROPERTY(int value READ value WRITE setValue NOTIFY valueChanged)
public:
    explicit ArcGauge(QWidget *parent = nullptr);

    int  value() const { return m_value; }
    void setValue(int v);

    void setLevel(const QString &level);
    void setLevelColor(const QColor &c);

    QSize sizeHint() const override { return QSize(340, 260); }

signals:
    void valueChanged(int v);

protected:
    void paintEvent(QPaintEvent *) override;

private:
    int     m_value = 0;
    QString m_level = "未评估";
    QColor  m_levelColor = QColor("#A0A0A0");
};

#endif // ARCGAUGE_H
