<p align="center">
  <img src="app/resources/icon.png" width="160" height="160" alt="KathFlow Studio Logo" style="border-radius: 20px;">
</p>

<h1 align="center">🎨 KathFlow Studio</h1>

<p align="center">
  <strong>Giải pháp chuyển đổi tài liệu trình chiếu thành video thuyết minh chuyên nghiệp tự động hóa từ đầu đến cuối.</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/Qt-6.5+-41CD52?style=for-the-badge&logo=qt&logoColor=white" alt="Qt">
  <img src="https://img.shields.io/badge/FFmpeg-Supported-007ACC?style=for-the-badge&logo=ffmpeg&logoColor=white" alt="FFmpeg">
</p>

---

## 🌟 Tính Năng Nổi Bật

* **🎙 Thuyết minh tự động bằng AI**:
  * Tích hợp các công nghệ chuyển đổi văn bản thành giọng nói (TTS) đỉnh cao như **Piper TTS (Offline)** và **Edge TTS (Online)**.
  * Hỗ trợ tải và lựa chọn nhiều giọng đọc chất lượng cao cực kỳ tự nhiên.

* **⏱ Đồng bộ hóa Slide theo giọng đọc**:
  * Đọc file âm thanh kèm dữ liệu mốc thời gian chi tiết (JSON timestamps) để tự động khớp cảnh chính xác từng mili-giây theo từ ngữ được nói.
  * Tự động gán nhãn vị trí hiển thị trực quan ngay trên trình soạn thảo kịch bản.

* **🎞 Hiệu ứng chuyển cảnh mượt mà**:
  * Tự động cài đặt hiệu ứng chuyển cảnh **Fade (0.5s)** mặc định cho toàn bộ tài liệu sau khi import giúp tiết kiệm thời gian tối đa.
  * Tùy chỉnh hiệu ứng (Fade, Wipe, Slide, Dissolve) và thời gian chuyển cảnh linh hoạt cho từng phân đoạn.

* **🎥 Hỗ trợ Opening / Ending riêng biệt**:
  * Dễ dàng gán video bất kỳ làm **Intro (Mở đầu)** hoặc **Ending (Kết thúc)**.
  * Hệ thống tự động tắt tiếng thuyết minh của các phân đoạn này, đẩy lùi thời gian bắt đầu đọc sang slide chính, và triệt tiêu mọi cảnh báo chưa gán nhãn trong UI.

* **🎚 Bộ trộn âm thanh chuyên sâu**:
  * Điều chỉnh âm lượng của âm thanh thuyết minh (TTS) và âm thanh gốc của video clip độc lập.
  * Tự động gán âm thanh gốc của video về mức **30%** khi import để làm nhạc nền tinh tế mà không át tiếng nói của AI.
  * Phím tắt tiện dụng hỗ trợ *Tắt tiếng tất cả* hoặc *Đặt 30% tất cả* chỉ với một cú click chuột.

* **📺 Xuất video sắc nét**:
  * Hỗ trợ xuất video chất lượng cao ở định dạng `.mp4`.
  * Tùy chọn nhiều cấu hình độ phân giải chuyên nghiệp: **Full HD (1080p), HD (720p), SD (480p)** và đặc biệt bổ sung chất lượng siêu nét **2K & 4K**.
  * Tự động kiểm tra trùng lặp tệp tin xuất, đưa ra cảnh báo và tự động đổi tên thêm hậu tố (ví dụ: `_2.mp4`) để bảo vệ dữ liệu cũ của bạn không bị ghi đè.

---

## 🛠 Yêu Cầu Hệ Thống

1. **Python 3.10** hoặc mới hơn.
2. **FFmpeg** đã được cài đặt và thêm vào biến môi trường hệ thống (`PATH`).

---

## 🚀 Hướng Dẫn Cài Đặt

Chương trình hỗ trợ script tự động hóa toàn bộ quy trình cài đặt môi trường trên Windows:

1. Tải toàn bộ mã nguồn của dự án về máy.
2. Nhấp đúp chuột chạy file **`install.bat`** để tự động:
   * Khởi tạo môi trường ảo Python (`.venv`).
   * Nâng cấp bộ quản lý gói `pip`.
   * Cài đặt đầy đủ các thư viện phụ thuộc trong file `requirements.txt`.

---

## 💻 Hướng Dẫn Sử Dụng

Sau khi cài đặt xong, bạn có hai cách cực kỳ đơn giản để khởi chạy studio:

### Cách 1: Sử dụng Launcher (Khuyên dùng)
* Nhấp đúp chuột vào file **`KathFlow.exe`** ở thư mục gốc của dự án.
* Đây là chương trình khởi chạy ngầm siêu nhẹ tích hợp icon đại diện chính thức của ứng dụng, giúp khởi động ứng dụng trực tiếp thông qua môi trường ảo mà không hiện lên màn hình dòng lệnh CMD màu đen.

### Cách 2: Sử dụng Script Bat
* Nhấp đúp chuột chạy file **`run.bat`** để mở ứng dụng thông qua môi trường ảo bằng giao diện dòng lệnh truyền thống.
