// Web Exam Client Logic with Real-time Proctoring

const EXAM_QUESTIONS = [
  {
    id: "q1",
    question: "Giao thức TCP giải quyết hiện tượng dính gói / xé gói (Fragmentation & Concatenation) trong luồng dữ liệu byte stream bằng cách nào?",
    options: [
      "A. Sử dụng Header chứa trường độ dài (Payload Length) cố định phía trước gói tin.",
      "B. Dựa vào cờ FIN của từng phân đoạn TCP.",
      "C. Tự động chuyển toàn bộ luồng truyền sang giao thức UDP datagram.",
      "D. Đợi bộ đệm Socket tràn hoàn toàn trước khi đọc dữ liệu."
    ],
    answer: "A"
  },
  {
    id: "q2",
    question: "Quá trình bắt tay 3 bước (Three-way Handshake) của giao thức TCP được thực hiện theo thứ tự cờ nào?",
    options: [
      "A. SYN -> ACK -> FIN",
      "B. SYN -> SYN-ACK -> ACK",
      "C. ACK -> SYN -> SYN-ACK",
      "D. PSH -> ACK -> URG"
    ],
    answer: "B"
  },
  {
    id: "q3",
    question: "Trong kiến trúc đa luồng của Socket Server, hàm nào sau đây được sử dụng để chấp nhận kết nối từ Client?",
    options: [
      "A. socket.bind()",
      "B. socket.listen()",
      "C. socket.accept()",
      "D. socket.connect()"
    ],
    answer: "C"
  },
  {
    id: "q4",
    question: "Độ dài tiêu chuẩn của Header nhị phân trong hệ thống RPMC/Exam Protocol của bài thi này là bao nhiêu byte?",
    options: [
      "A. 8 bytes",
      "B. 12 bytes (Magic: 2B, Ver: 1B, Res: 1B, Len: 4B, Frame: 2B, Cmd: 2B)",
      "C. 20 bytes",
      "D. 16 bytes"
    ],
    answer: "B"
  },
  {
    id: "q5",
    question: "Trong quy trình Scrum, vai trò nào chịu trách nhiệm thiết lập tiêu chí nghiệm thu và quy chế điểm phạt cho phòng thi?",
    options: [
      "A. Scrum Master (SM)",
      "B. Product Owner (PO) / Giảng viên",
      "C. Development Team / Học sinh",
      "D. Agile Coach"
    ],
    answer: "B"
  }
];

class ExamApp {
  constructor() {
    this.studentId = "";
    this.studentName = "";
    this.config = {
      initial_score: 10.0,
      penalty_per_violation: 1.0,
      max_violations: 10,
      duration_minutes: 45
    };
    this.currentScore = 10.0;
    this.violationCount = 0;
    this.isExamStarted = false;
    this.isExamLocked = false;
    this.isExamSubmitted = false;
    this.lastViolationTime = 0;
    this.timerInterval = null;
    this.remainingSeconds = 45 * 60;
    this.eventSource = null;

    this.initElements();
    this.bindEvents();
    this.fetchConfig();
  }

  initElements() {
    // Stages
    this.loginStage = document.getElementById("login-stage");
    this.readyStage = document.getElementById("ready-stage");
    this.examStage = document.getElementById("exam-stage");
    this.resultStage = document.getElementById("result-stage");

    // Forms & Inputs
    this.loginForm = document.getElementById("login-form");
    this.studentIdInput = document.getElementById("student-id");
    this.studentNameInput = document.getElementById("student-name");
    this.btnStartExam = document.getElementById("btn-start-exam");
    this.btnSubmitExam = document.getElementById("btn-submit-exam");

    // HUD Elements
    this.hudStudentInfo = document.getElementById("hud-student-info");
    this.hudScore = document.getElementById("hud-score");
    this.hudViolations = document.getElementById("hud-violations");
    this.examTimer = document.getElementById("exam-timer");
    this.questionsContainer = document.getElementById("questions-container");

    // Modals
    this.lockedOverlay = document.getElementById("locked-overlay");
    this.lockedReason = document.getElementById("locked-reason");
    this.alertToast = document.getElementById("alert-toast");
    this.toastTitle = document.getElementById("toast-title");
    this.toastMessage = document.getElementById("toast-message");
    this.supervisorModal = document.getElementById("supervisor-warning-modal");
    this.supervisorMsgText = document.getElementById("supervisor-message-text");
    this.btnAckWarning = document.getElementById("btn-ack-warning");
  }

  bindEvents() {
    // Form submit
    this.loginForm.addEventListener("submit", (e) => this.handleLogin(e));
    this.btnStartExam.addEventListener("click", () => this.startExam());
    this.btnSubmitExam.addEventListener("click", () => this.submitExam());
    this.btnAckWarning.addEventListener("click", () => {
      this.supervisorModal.classList.remove("active");
    });

    // Prevent context menu
    window.addEventListener("contextmenu", (e) => e.preventDefault());

    // Proctoring event listeners
    document.addEventListener("visibilitychange", () => {
      if (document.hidden && this.isExamStarted && !this.isExamSubmitted && !this.isExamLocked) {
        this.reportViolation("TAB_SWITCH", "Chuyển tab hoặc thu nhỏ trình duyệt");
      }
    });

    window.addEventListener("blur", () => {
      if (this.isExamStarted && !this.isExamSubmitted && !this.isExamLocked) {
        this.reportViolation("BLUR", "Mất focus chuột khỏi màn hình thi (Alt+Tab hoặc click ra ngoài)");
      }
    });

    document.addEventListener("fullscreenchange", () => {
      if (!document.fullscreenElement && this.isExamStarted && !this.isExamSubmitted && !this.isExamLocked) {
        this.reportViolation("EXIT_FULLSCREEN", "Thoát khỏi chế độ Toàn Màn Hình (Fullscreen)");
      }
    });

    // Block keyboard shortcuts
    window.addEventListener("keydown", (e) => {
      // F12 or Ctrl+Shift+I or Ctrl+Shift+J or Alt+Tab or Ctrl+R
      if (
        e.key === "F12" ||
        (e.ctrlKey && e.shiftKey && (e.key === "I" || e.key === "J" || e.key === "C")) ||
        (e.ctrlKey && e.key === "u") ||
        (e.altKey && e.key === "Tab")
      ) {
        e.preventDefault();
        if (this.isExamStarted && !this.isExamLocked) {
          this.reportViolation("DEVTOOLS_ATTEMPT", "Cố gắng mở DevTools hoặc phím tắt bị cấm");
        }
      }
    });
  }

  async fetchConfig() {
    try {
      const res = await fetch("/api/exam/config");
      if (res.ok) {
        this.config = await res.json();
        document.getElementById("info-init-score").textContent = this.config.initial_score.toFixed(1);
        document.getElementById("info-penalty").textContent = `-${this.config.penalty_per_violation.toFixed(1)} đ`;
        document.getElementById("info-max-violation").textContent = `${this.config.max_violations} lần`;
        document.getElementById("info-duration").textContent = `${this.config.duration_minutes} phút`;
        this.currentScore = this.config.initial_score;
        this.remainingSeconds = this.config.duration_minutes * 60;
      }
    } catch (err) {
      console.warn("Could not fetch remote config, using defaults", err);
    }
  }

  async handleLogin(e) {
    e.preventDefault();
    this.studentId = this.studentIdInput.value.trim().toUpperCase();
    this.studentName = this.studentNameInput.value.trim();

    if (!this.studentId) return;

    try {
      const res = await fetch("/api/exam/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          student_id: this.studentId,
          name: this.studentName
        })
      });
      const data = await res.json();
      if (data.status === "ok") {
        if (data.config) this.config = data.config;
        this.currentScore = data.student.score;
        this.violationCount = data.student.violation_count || 0;

        document.getElementById("ready-welcome").textContent = `Chào mừng: ${this.studentName} (${this.studentId})`;
        this.switchStage(this.loginStage, this.readyStage);
      } else {
        alert(data.error || "Đăng ký thất bại");
      }
    } catch (err) {
      alert("Lỗi kết nối tới Server LAN. Vui lòng kiểm tra địa chỉ IP.");
    }
  }

  async startExam() {
    // Request Fullscreen
    try {
      if (document.documentElement.requestFullscreen) {
        await document.documentElement.requestFullscreen();
      }
    } catch (err) {
      console.warn("Fullscreen permission denied or not supported", err);
    }

    this.isExamStarted = true;
    this.switchStage(this.readyStage, this.examStage);

    // Update HUD
    this.hudStudentInfo.textContent = `${this.studentName} (${this.studentId})`;
    this.updateHud();

    // Render Questions
    this.renderQuestions();

    // Start Timer
    this.startTimer();

    // Connect SSE for real-time supervisor alerts
    this.connectSSE();
  }

  renderQuestions() {
    this.questionsContainer.innerHTML = EXAM_QUESTIONS.map((q, idx) => `
      <div class="question-card" id="card-${q.id}">
        <div class="question-number">CÂU HỎI ${idx + 1} / ${EXAM_QUESTIONS.length}</div>
        <div class="question-text">${q.question}</div>
        <div class="options-list">
          ${q.options.map((opt, optIdx) => {
            const letter = opt.substring(0, 1);
            return `
              <label class="option-label">
                <input type="radio" name="ans-${q.id}" value="${letter}">
                <span class="option-text">${opt}</span>
              </label>
            `;
          }).join("")}
        </div>
      </div>
    `).join("");
  }

  startTimer() {
    this.timerInterval = setInterval(() => {
      this.remainingSeconds--;
      if (this.remainingSeconds <= 0) {
        clearInterval(this.timerInterval);
        this.examTimer.textContent = "00:00";
        alert("Hết giờ làm bài! Hệ thống tự động nộp bài.");
        this.submitExam();
        return;
      }
      const mins = Math.floor(this.remainingSeconds / 60);
      const secs = this.remainingSeconds % 60;
      this.examTimer.textContent = `${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
    }, 1000);
  }

  connectSSE() {
    if (this.eventSource) this.eventSource.close();
    this.eventSource = new EventSource(`/api/exam/events?student_id=${encodeURIComponent(this.studentId)}`);

    this.eventSource.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        this.handleRemoteEvent(payload);
      } catch (e) {}
    };

    this.eventSource.onerror = () => {
      console.warn("SSE connection interrupted, retrying...");
    };
  }

  handleRemoteEvent(payload) {
    if (payload.type === "DIRECT_WARNING") {
      this.supervisorMsgText.textContent = payload.message || "Giám thị nhắc nhở nghiêm túc làm bài!";
      this.supervisorModal.classList.add("active");
    } else if (payload.type === "STUDENT_LOCKED") {
      if (payload.student && payload.student.student_id === this.studentId) {
        this.lockExam(payload.reason || "Giám thị cưỡng chế đình chỉ bài thi");
      }
    } else if (payload.type === "CONFIG_UPDATE") {
      this.config = payload.config;
      this.updateHud();
    }
  }

  async reportViolation(eventType, detail) {
    const now = Date.now();
    // Debounce violation reports by 1.5 seconds to avoid spamming bursts
    if (now - this.lastViolationTime < 1500) return;
    this.lastViolationTime = now;

    try {
      const res = await fetch("/api/exam/violation", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          student_id: this.studentId,
          event: eventType,
          detail: detail,
          timestamp: now / 1000
        })
      });

      if (res.ok) {
        const data = await res.json();
        this.currentScore = data.student.score;
        this.violationCount = data.student.violation_count;
        this.updateHud();

        // Show Toast
        this.showToast(`CẢNH BÁO VI PHẠM: ${detail}`, `Bị trừ ${data.violation.deduction.toFixed(1)} điểm!`);

        // Check if locked
        if (data.student.status === "LOCKED" || this.violationCount >= this.config.max_violations) {
          this.lockExam(`Bạn đã vi phạm ${this.violationCount}/${this.config.max_violations} lần.`);
        }
      }
    } catch (err) {
      console.error("Failed to report violation", err);
    }
  }

  showToast(title, msg) {
    this.toastTitle.textContent = title;
    this.toastMessage.textContent = msg;
    this.alertToast.classList.add("active");
    setTimeout(() => {
      this.alertToast.classList.remove("active");
    }, 4500);
  }

  updateHud() {
    this.hudScore.textContent = this.currentScore.toFixed(1);
    this.hudViolations.textContent = `${this.violationCount} / ${this.config.max_violations}`;
  }

  lockExam(reason) {
    this.isExamLocked = true;
    if (this.timerInterval) clearInterval(this.timerInterval);
    this.lockedReason.textContent = reason;
    this.lockedOverlay.classList.add("active");
  }

  async submitExam() {
    if (this.isExamSubmitted) return;
    if (!confirm("Bạn có chắc chắn muốn nộp bài thi không?")) return;

    this.isExamSubmitted = true;
    if (this.timerInterval) clearInterval(this.timerInterval);

    // Collect answers
    const answers = {};
    EXAM_QUESTIONS.forEach(q => {
      const checked = document.querySelector(`input[name="ans-${q.id}"]:checked`);
      answers[q.id] = checked ? checked.value : null;
    });

    try {
      const res = await fetch("/api/exam/submit", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          student_id: this.studentId,
          answers: answers
        })
      });
      const data = await res.json();
      this.showResult(data.student);
    } catch (err) {
      alert("Lỗi nộp bài thi!");
    }
  }

  showResult(student) {
    this.switchStage(this.examStage, this.resultStage);
    document.getElementById("result-student-name").textContent = `Thí sinh: ${this.studentName} (${this.studentId})`;
    document.getElementById("result-final-score").textContent = student.score.toFixed(1);

    const details = document.getElementById("result-details");
    details.innerHTML = `
      <div style="margin-top: 16px; font-size: 14px; color: #8b949e; line-height: 1.8;">
        <p>Tổng số lần vi phạm trong phòng thi: <strong style="color: #f85149;">${student.violation_count} lần</strong></p>
        <p>Mức trừ điểm: <strong>-${(student.violation_count * this.config.penalty_per_violation).toFixed(1)} điểm</strong></p>
        <p>Trạng thái cuối cùng: <strong style="color: #3fb950;">${student.status}</strong></p>
      </div>
    `;
  }

  switchStage(fromStage, toStage) {
    fromStage.classList.remove("active");
    toStage.classList.add("active");
  }
}

// Start on DOM ready
document.addEventListener("DOMContentLoaded", () => {
  new ExamApp();
});
