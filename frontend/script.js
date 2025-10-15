let pc = new RTCPeerConnection();
let ws = new WebSocket("ws://localhost:8001/ws");

const localVideo = document.getElementById("localVideo");
const remoteVideo = document.getElementById("remoteVideo");
const startBtn = document.getElementById("startBtn");

navigator.mediaDevices.getUserMedia({ video: true, audio: true })
  .then(stream => {
    localVideo.srcObject = stream;
    stream.getTracks().forEach(track => pc.addTrack(track, stream));
  });

pc.ontrack = (event) => {
  remoteVideo.srcObject = event.streams[0];
};

pc.onicecandidate = (event) => {
  if (event.candidate) {
    ws.send(JSON.stringify({ type: "candidate", candidate: event.candidate }));
  }
};

ws.onmessage = async (event) => {
  const msg = JSON.parse(event.data);

  if (msg.type === "offer") {
    await pc.setRemoteDescription(new RTCSessionDescription(msg));
    const answer = await pc.createAnswer();
    await pc.setLocalDescription(answer);
    ws.send(JSON.stringify(pc.localDescription));
  } else if (msg.type === "answer") {
    await pc.setRemoteDescription(new RTCSessionDescription(msg));
  } else if (msg.type === "candidate") {
    await pc.addIceCandidate(msg.candidate);
  }
};

startBtn.onclick = async () => {
  const offer = await pc.createOffer();
  await pc.setLocalDescription(offer);
  ws.send(JSON.stringify(offer));
};
