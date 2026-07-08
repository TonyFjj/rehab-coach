# RK3588 蓝牙网关

这个目录提供一个蓝牙 SPP 网关示例，用来把 RK3588 上 Qt 康复程序保存的训练记录、评估得分、细分方向得分和医疗建议同步到手机 App。

## 推荐运行方式

在 RK3588 上先确保蓝牙可被发现，并让手机在系统蓝牙设置里完成配对：

```bash
bluetoothctl
power on
agent on
default-agent
discoverable on
pairable on
```

安装 PyBluez/BlueZ 绑定：

```bash
sudo apt update
sudo apt install -y bluez python3-bluez
```

启动网关：

```bash
python3 bt_rehab_gateway.py --project-root /home/elf/Desktop/rknn
```

如果 Qt 已经把 `latest_assessment.json` 写到其他目录，可显式指定：

```bash
REHAB_QT_DATA_FILE=/home/elf/.local/share/prograss_copy/latest_assessment.json \
python3 bt_rehab_gateway.py --project-root /home/elf/Desktop/rknn
```

也可以直接指定 Qt 数据目录或各记录文件：

```bash
REHAB_QT_STORAGE_DIR=/home/elf/.local/share/prograss_copy \
python3 bt_rehab_gateway.py --project-root /home/elf/Desktop/rknn
```

```bash
REHAB_QT_TRAINING_RECORDS_FILE=/path/to/training_records.json \
REHAB_QT_MEDICAL_RECORDS_FILE=/path/to/medical_advice_records.json \
REHAB_QT_DATA_FILE=/path/to/latest_assessment.json \
python3 bt_rehab_gateway.py --project-root /home/elf/Desktop/rknn
```

## 数据来源优先级

1. Qt 的 `training_records.json`：每次训练记录、综合得分、完成度、动作/功能块得分和训练建议。
2. Qt 的 `medical_advice_records.json`：每次评估记录、综合得分、六维细分得分和医疗建议。
3. Qt 的 `latest_assessment.json`：最新评估，用于没有历史记录时兜底。
4. `rehab-coach-rknn/data/imu/assessment_result.txt`：后端原始评估结果兜底。

手机连接后，网关会先发送 `sync_snapshot` 全量快照；运行期间如果上述 JSON 文件变化，会继续推送新的快照。手机端按 `record_id` 去重保存。

## systemd 服务

把 `bt_rehab_gateway.service` 中的路径改成 RK3588 实际路径后：

```bash
sudo cp bt_rehab_gateway.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now bt_rehab_gateway.service
```
