document.addEventListener("DOMContentLoaded", () => {
  const reader = document.getElementById("qr-reader");
  if (!reader) return;

  const eventId = Number(reader.dataset.eventId);
  const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content;
  const statusLine = document.getElementById("scanner-status");
  const warningAlert = document.getElementById("warning-alert");
  const warningMessage = document.getElementById("warning-message");
  const successToastElement = document.getElementById("success-toast");
  const successToastMessage = document.getElementById("success-toast-message");
  const errorModalElement = document.getElementById("error-modal");
  const errorModalMessage = document.getElementById("error-modal-message");

  if (!window.Html5Qrcode) {
    statusLine.textContent = "The QR scanner library did not load. Refresh the page and try again.";
    return;
  }

  const scanner = new Html5Qrcode("qr-reader", {
    formatsToSupport: [Html5QrcodeSupportedFormats.QR_CODE],
    verbose: false,
  });
  const scannerConfig = { fps: 10, qrbox: { width: 250, height: 250 } };
  const successToast = bootstrap.Toast.getOrCreateInstance(successToastElement, {
    autohide: false,
  });
  const errorModal = bootstrap.Modal.getOrCreateInstance(errorModalElement, {
    backdrop: "static",
    keyboard: false,
  });
  let handlingScan = false;

  function hideFeedback() {
    warningAlert.classList.add("d-none");
    successToast.hide();
    errorModal.hide();
  }

  function showFeedback(status, message) {
    hideFeedback();

    if (status === "success") {
      successToastMessage.textContent = message;
      successToast.show();
    } else if (status === "warning") {
      warningMessage.textContent = message;
      warningAlert.classList.remove("d-none");
    } else {
      errorModalMessage.textContent = message;
      errorModal.show();
    }
  }

  async function handleScan(decodedText) {
    if (handlingScan) return;
    handlingScan = true;
    statusLine.textContent = "Ticket scanned. Verifying...";

    try {
      // Freeze the camera image and pause decoding while this token is checked.
      scanner.pause(true);
    } catch (error) {
      console.error("Could not pause the QR scanner:", error);
    }

    try {
      const response = await fetch("/api/verify-ticket", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrfToken,
        },
        body: JSON.stringify({ qr_token: decodedText.trim(), event_id: eventId }),
      });
      const result = await response.json();
      showFeedback(result.status, result.message || "Ticket verification failed.");
    } catch (error) {
      console.error("Ticket verification request failed:", error);
      showFeedback("error", "Could not reach the verification server. Please try again.");
    }

    window.setTimeout(() => {
      hideFeedback();
      try {
        scanner.resume();
        statusLine.textContent = "Camera is active. Scan the next ticket.";
      } catch (error) {
        console.error("Could not resume the QR scanner:", error);
        statusLine.textContent = "Could not resume the camera. Refresh the page to scan again.";
      }
      handlingScan = false;
    }, 3000);
  }

  statusLine.textContent = "Allow camera access to start scanning.";
  scanner
    .start(
      { facingMode: "environment" },
      scannerConfig,
      handleScan,
      () => {},
    )
    .then(() => {
      statusLine.textContent = "Camera is active. Scan an event ticket QR code.";
    })
    .catch((error) => {
      console.error("Could not start the QR scanner:", error);
      statusLine.textContent = "Camera access failed. Check browser permissions and try again.";
    });
});
