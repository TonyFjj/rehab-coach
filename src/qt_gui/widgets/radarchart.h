#ifndef RADARCHART_H
#define RADARCHART_H

#include <QWidget>
#include <QMap>
#include <QStringList>

class RadarChart : public QWidget
{
    Q_OBJECT
public:
    explicit RadarChart(QWidget *parent = nullptr);

    void setDimensions(const QStringList &names);
    void setValues(const QMap<QString, double> &vals); // 0.0 ~ 1.0
    void clear();

    QSize sizeHint() const override { return QSize(240, 240); }
    QSize minimumSizeHint() const override { return QSize(220, 220); }

protected:
    void paintEvent(QPaintEvent *) override;

private:
    QStringList m_dimNames;
    QMap<QString, double> m_values;
};

#endif // RADARCHART_H
