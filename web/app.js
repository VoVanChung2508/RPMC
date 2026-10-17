// Web Exam Client Logic with Real-time Proctoring & PostgreSQL Exam Integration

class ExamApp {
  constructor() {
    this.studentId = "";
    this.studentName = "";
    this.config = {
      initial_score: 10.0,
      penalty_per_violation: 1.0,
      max_violations: 3,
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
    this.questions = [];
    this.submissions = {};
    this.token = sessionStorage.getItem("rpmc_student_token") || "";
    this.saveQueue = [];
    this.isProcessingSaveQueue = false;

    this.initElements();
    this.bindEvents();
    this.initApp();
  }

  authHeaders(extra = {}) {
    const headers = { ...extra };
    if (this.token) {
      headers["X-Student-Token"] = this.token;
    }
    return headers;
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
    this.saveStatusBadge = document.getElementById("save-status-badge");
    this.saveStatusIcon = document.getElementById("save-status-icon");
    this.saveStatusText = document.getElementById("save-status-text");

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

  updateSaveStatus(status) {
    if (!this.saveStatusBadge) return;
    this.saveStatusBadge.classList.remove("saved", "saving", "error");
    if (status === "saving") {
      this.saveStatusBadge.classList.add("saving");
      if (this.saveStatusIcon) this.saveStatusIcon.textContent = "⏳";
      if (this.saveStatusText) this.saveStatusText.textContent = "Đang lưu...";
    } else if (status === "error") {
      this.saveStatusBadge.classList.add("error");
      if (this.saveStatusIcon) this.saveStatusIcon.textContent = "⚠️";
      if (this.saveStatusText) this.saveStatusText.textContent = "Lỗi lưu đáp án";
    } else {
      this.saveStatusBadge.classList.add("saved");
      if (this.saveStatusIcon) this.saveStatusIcon.textContent = "✓";
      if (this.saveStatusText) this.saveStatusText.textContent = "Đã lưu";
    }
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

  async initApp() {
    await this.fetchConfig();
    this.checkSessionRestoration();
  }

  async fetchConfig() {
    try {
      const res = await fetch("/api/exam/config");
      if (res.ok) {
        this.config = await res.json();
        const initScoreEl = document.getElementById("info-init-score");
        if (initScoreEl) initScoreEl.textContent = this.config.initial_score.toFixed(1);
        const penEl = document.getElementById("info-penalty");
        if (penEl) penEl.textContent = `-${this.config.penalty_per_violation.toFixed(1)} đ`;
        const maxVEl = document.getElementById("info-max-violation");
        if (maxVEl) maxVEl.textContent = `${this.config.max_violations} lần`;
        const durEl = document.getElementById("info-duration");
        if (durEl) durEl.textContent = `${this.config.duration_minutes} phút`;

        if (this.config.remaining_seconds !== undefined) {
          this.remainingSeconds = this.config.remaining_seconds;
        } else {
          this.remainingSeconds = this.config.duration_minutes * 60;
        }
      }
    } catch (err) {
      console.warn("Không thể tải cấu hình từ server, sử dụng mặc định:", err);
    }
  }

  async checkSessionRestoration() {
    // Khôi phục phiên làm bài khi thí sinh F5 tải lại trang
    const savedId = sessionStorage.getItem("rpmc_student_id");
    const savedName = sessionStorage.getItem("rpmc_student_name");
    const savedToken = sessionStorage.getItem("rpmc_student_token");
    if (!savedId || !savedToken) return;

    this.token = savedToken;
    try {
      const res = await fetch(`/api/exam/status?student_id=${encodeURIComponent(savedId)}`, {
        headers: this.authHeaders()
      });
      if (res.ok) {
        const student = await res.json();
        this.studentId = savedId;
        this.studentName = savedName || student.name || savedId;
        this.currentScore = student.score;
        this.violationCount = student.violation_count || 0;

        if (student.remaining_seconds !== undefined) {
          this.remainingSeconds = student.remaining_seconds;
        }

        if (student.status === "SUBMITTED") {
          this.isExamSubmitted = true;
          this.showResult(student);
          return;
        }

        if (student.status === "LOCKED") {
          this.lockExam(student.warning_message || "Bài thi đã bị khóa");
          return;
        }

        // Tự động khôi phục giao diện làm bài thi
        this.isExamStarted = true;
        this.switchStage(this.loginStage, this.examStage);
        this.hudStudentInfo.textContent = `${this.studentName} (${this.studentId})`;
        this.updateHud();
        await this.loadAndRenderQuestions();
        await this.restoreSubmissions();
        this.startTimer();
        this.connectSSE();
      }
    } catch (err) {
      console.warn("Không thể khôi phục phiên từ server:", err);
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
        this.token = data.token || "";
        sessionStorage.setItem("rpmc_student_token", this.token);
        sessionStorage.setItem("rpmc_student_id", this.studentId);
        sessionStorage.setItem("rpmc_student_name", this.studentName);

        if (data.config) this.config = data.config;
        if (data.config && data.config.remaining_seconds !== undefined) {
          this.remainingSeconds = data.config.remaining_seconds;
        }
        this.currentScore = data.student.score;
        this.violationCount = data.student.violation_count || 0;

        document.getElementById("ready-welcome").textContent = `Chào mừng: ${this.studentName} (${this.studentId})`;
        this.switchStage(this.loginStage, this.readyStage);
      } else {
        alert(data.error || "Đăng ký thất bại");
      }
    } catch (err) {
      alert("Lỗi kết nối tới Server LAN. Vui lòng kiểm tra địa chỉ IP và trạng thái server.");
    }
  }

  async startExam() {
    try {
      if (document.documentElement.requestFullscreen) {
        await document.documentElement.requestFullscreen();
      }
    } catch (err) {
      console.warn("Fullscreen permission denied or not supported", err);
    }

    this.isExamStarted = true;
    this.switchStage(this.readyStage, this.examStage);

    this.hudStudentInfo.textContent = `${this.studentName} (${this.studentId})`;
    this.updateHud();

    await this.loadAndRenderQuestions();
    await this.restoreSubmissions();
    this.startTimer();
    this.connectSSE();
  }

  async loadAndRenderQuestions() {
    try {
      const res = await fetch(`/api/exam/questions?student_id=${encodeURIComponent(this.studentId)}`, {
        headers: this.authHeaders()
      });
      const data = await res.json();
      if (res.ok && data.questions) {
        this.questions = data.questions;
        if (data.remaining_seconds !== undefined) {
          this.remainingSeconds = data.remaining_seconds;
        }
        this.renderQuestions();
      } else {
        this.questionsContainer.innerHTML = `<div class="error-msg">Không tải được đề thi: ${data.error || "Chưa có câu hỏi"}</div>`;
      }
    } catch (err) {
      this.questionsContainer.innerHTML = `<div class="error-msg">Lỗi kết nối khi nạp đề thi từ server.</div>`;
    }
  }

  renderQuestions() {
    if (!this.questions || this.questions.length === 0) {
      this.questionsContainer.innerHTML = `<div class="info-msg">Chưa có câu hỏi nào cho kỳ thi này.</div>`;
      return;
    }

    this.questionsContainer.innerHTML = this.questions.map((q, idx) => `
      <div class="question-card" id="card-${q.question_id}">
        <div class="question-number">CÂU HỎI ${idx + 1} / ${this.questions.length}</div>
        <div class="question-text">${this.escapeHtml(q.content)}</div>
        <div class="options-list">
          ${q.options.map(opt => {
            const val = opt.orig || opt.label;
            return `
              <label class="option-label" data-qid="${q.question_id}" data-opt="${val}">
                <input type="radio" name="ans-${q.question_id}" value="${val}">
                <span class="option-text"><strong>${opt.label}.</strong> ${this.escapeHtml(opt.content)}</span>
              </label>
            `;
          }).join("")}
        </div>
      </div>
    `).join("");

    // Gắn sự kiện lưu nháp tức thì cho từng đáp án
    this.questionsContainer.querySelectorAll('input[type="radio"]').forEach(radio => {
      radio.addEventListener("change", (e) => {
        const qid = e.target.name.replace("ans-", "");
        const chosen = e.target.value;
        this.saveDraft(qid, chosen);
      });
    });
  }

  async restoreSubmissions() {
    try {
      const res = await fetch(`/api/exam/submissions?student_id=${encodeURIComponent(this.studentId)}`, {
        headers: this.authHeaders()
      });
      if (res.ok) {
        const data = await res.json();
        this.submissions = data.submissions || {};
        for (const [qid, chosen] of Object.entries(this.submissions)) {
          const radio = document.querySelector(`input[name="ans-${qid}"][value="${chosen}"]`);
          if (radio) {
            radio.checked = true;
          }
        }
      }
    } catch (err) {
      console.warn("Không thể tải các đáp án đã lưu:", err);
    }
  }

  saveDraft(questionId, chosen) {
    if (this.isExamLocked || this.isExamSubmitted) return;

    // Cập nhật ngay bộ nhớ tạm phía client để không bị mất lựa chọn khi người dùng bấm nhanh
    this.submissions[questionId] = chosen;

    // Đưa vào hàng đợi lưu draft (nếu câu này đã có trong hàng đợi chờ gửi, ghi đè đáp án mới nhất)
    const existingIndex = this.saveQueue.findIndex(item => item.questionId === questionId);
    if (existingIndex >= 0) {
      this.saveQueue[existingIndex].chosen = chosen;
      this.saveQueue[existingIndex].retries = 0;
    } else {
      this.saveQueue.push({
        questionId: questionId,
        chosen: chosen,
        retries: 0
      });
    }

    this.processSaveQueue();
  }

  async processSaveQueue() {
    if (this.isProcessingSaveQueue) return;
    if (this.saveQueue.length === 0) return;

    this.isProcessingSaveQueue = true;
    this.updateSaveStatus("saving");

    while (this.saveQueue.length > 0) {
      const item = this.saveQueue[0];
      try {
        const res = await fetch("/api/exam/save_draft", {
          method: "POST",
          headers: this.authHeaders({ "Content-Type": "application/json" }),
          body: JSON.stringify({
            student_id: this.studentId,
            question_id: item.questionId,
            chosen: item.chosen
          })
        });

        if (res.ok) {
          // Lưu thành công câu hiện tại
          this.saveQueue.shift();
        } else if (res.status === 429) {
          // Gặp 429 Rate Limit: Thử lại có giới hạn
          item.retries = (item.retries || 0) + 1;
          if (item.retries > 5) {
            console.error("Vượt quá số lần thử lại khi lưu câu", item.questionId);
            this.updateSaveStatus("error");
            this.saveQueue.shift();
          } else {
            // Chờ trước khi gửi lại (exponential backoff nhẹ)
            await new Promise(r => setTimeout(r, 200 * item.retries));
          }
        } else if (res.status === 403) {
          const data = await res.json().catch(() => ({}));
          this.updateSaveStatus("error");
          alert(data.error || "Không thể lưu đáp án (Kỳ thi đã kết thúc hoặc bài thi bị khóa)!");
          if (data.error && data.error.includes("khóa")) {
            this.lockExam(data.error);
          } else if (data.error && data.error.includes("kết thúc")) {
            this.submitExam(true);
          }
          this.saveQueue = [];
          break;
        } else {
          item.retries = (item.retries || 0) + 1;
          if (item.retries > 3) {
            this.updateSaveStatus("error");
            this.saveQueue.shift();
          } else {
            await new Promise(r => setTimeout(r, 300));
          }
        }
      } catch (networkErr) {
        // Lỗi mạng: thử lại có giới hạn
        console.warn("Lỗi mạng khi lưu nháp:", networkErr);
        item.retries = (item.retries || 0) + 1;
        if (item.retries > 5) {
          this.updateSaveStatus("error");
          this.saveQueue.shift();
        } else {
          await new Promise(r => setTimeout(r, 250 * item.retries));
        }
      }
    }

    this.isProcessingSaveQueue = false;
    if (this.saveQueue.length === 0) {
      this.updateSaveStatus("saved");
    }
  }

  startTimer() {
    if (this.timerInterval) clearInterval(this.timerInterval);

    const updateTimerDisplay = () => {
      if (this.remainingSeconds <= 0) {
        clearInterval(this.timerInterval);
        this.examTimer.textContent = "00:00";
        alert("Hết giờ làm bài! Hệ thống tự động thu bài và chấm điểm.");
        this.submitExam(true);
        return;
      }
      const mins = Math.floor(this.remainingSeconds / 60);
      const secs = this.remainingSeconds % 60;
      this.examTimer.textContent = `${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
    };

    updateTimerDisplay();
    this.timerInterval = setInterval(() => {
      this.remainingSeconds--;
      updateTimerDisplay();
    }, 1000);
  }

  connectSSE() {
    if (this.eventSource) this.eventSource.close();
    this.eventSource = new EventSource(`/api/exam/events?student_id=${encodeURIComponent(this.studentId)}&token=${encodeURIComponent(this.token)}`);

    this.eventSource.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        this.handleRemoteEvent(payload);
      } catch (e) {}
    };

    this.eventSource.onerror = () => {
      console.warn("Mất kết nối SSE, đang tự động thử lại...");
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
      if (payload.config && payload.config.status === "FINISHED") {
        this.submitExam(true);
      }
      this.updateHud();
    }
  }

  async reportViolation(eventType, detail) {
    const now = Date.now();
    if (now - this.lastViolationTime < 1500) return;
    this.lastViolationTime = now;

    try {
      const res = await fetch("/api/exam/violation", {
        method: "POST",
        headers: this.authHeaders({ "Content-Type": "application/json" }),
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

        this.showToast(`CẢNH BÁO VI PHẠM: ${detail}`, `Bị trừ ${data.violation.deduction.toFixed(1)} điểm!`);

        if (data.student.status === "LOCKED" || this.violationCount >= this.config.max_violations) {
          this.lockExam(`Bạn đã vi phạm ${this.violationCount}/${this.config.max_violations} lần.`);
        }
      }
    } catch (err) {
      console.error("Lỗi gửi cảnh báo vi phạm:", err);
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

  async submitExam(isAuto = false) {
    if (this.isExamSubmitted) return;
    if (!isAuto && !confirm("Bạn có chắc chắn muốn nộp bài thi không?")) return;

    this.isExamSubmitted = true;
    if (this.timerInterval) clearInterval(this.timerInterval);

    // Thu thập toàn bộ đáp án đã chọn
    const answers = {};
    if (this.questions && this.questions.length > 0) {
      this.questions.forEach(q => {
        const checked = document.querySelector(`input[name="ans-${q.question_id}"]:checked`);
        if (checked) {
          answers[q.question_id] = checked.value;
        }
      });
    }

    try {
      const res = await fetch("/api/exam/submit", {
        method: "POST",
        headers: this.authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({
          student_id: this.studentId,
          answers: answers
        })
      });
      const data = await res.json();
      if (res.ok) {
        this.showResult(data.student);
      } else {
        alert(data.error || "Lỗi khi nộp bài!");
      }
    } catch (err) {
      alert("Lỗi kết nối khi nộp bài thi!");
    }
  }

  showResult(student) {
    this.switchStage(this.examStage, this.resultStage);
    this.switchStage(this.readyStage, this.resultStage);
    this.switchStage(this.loginStage, this.resultStage);

    document.getElementById("result-student-name").textContent = `Thí sinh: ${this.studentName} (${this.studentId})`;
    document.getElementById("result-final-score").textContent = Number(student.score).toFixed(1);

    const details = document.getElementById("result-details");
    details.innerHTML = `
      <div style="margin-top: 16px; font-size: 14px; color: #8b949e; line-height: 1.8;">
        <p>Tổng số lần vi phạm trong phòng thi: <strong style="color: #f85149;">${student.violation_count || 0} lần</strong></p>
        <p>Mức trừ điểm: <strong>-${((student.violation_count || 0) * this.config.penalty_per_violation).toFixed(1)} điểm</strong></p>
        <p>Trạng thái cuối cùng: <strong style="color: #3fb950;">${student.status}</strong></p>
      </div>
    `;
  }

  switchStage(fromStage, toStage) {
    if (fromStage) fromStage.classList.remove("active");
    if (toStage) toStage.classList.add("active");
  }

  escapeHtml(str) {
    if (!str) return "";
    return str
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }
}

// Khởi chạy khi DOM sẵn sàng
document.addEventListener("DOMContentLoaded", () => {
  new ExamApp();
});
