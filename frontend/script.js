// --- DOM Elements ---
const setupDiv = document.getElementById("setup");
const roomDiv = document.getElementById("room");
const roomInput = document.getElementById("roomInput");
const nameInput = document.getElementById("nameInput");
const joinBtn = document.getElementById("joinBtn");
const videosDiv = document.getElementById("videos");
const muteBtn = document.getElementById("muteBtn");
const cameraBtn = document.getElementById("cameraBtn");
const shareScreenBtn = document.getElementById("shareScreenBtn");
const endBtn = document.getElementById("endBtn");

// --- WebRTC Globals ---
let ws;
let localStream;
let cameraStream;
let pcs = {};
let myId = Math.random().toString(36).substring(2, 9);
let myName = "";

const audioContext = new (window.AudioContext || window.webkitAudioContext)();
const SPEAKING_THRESHOLD = 5;

// --- All functions (monitorAudioLevel, createVideoPlayer, etc.) remain the same ---

function monitorAudioLevel(stream, videoContainerId) {
    if (!audioContext || !stream.getAudioTracks().length) return;
    const analyser = audioContext.createAnalyser();
    const source = audioContext.createMediaStreamSource(stream);
    source.connect(analyser);
    analyser.fftSize = 512;
    const bufferLength = analyser.frequencyBinCount;
    const dataArray = new Uint8Array(bufferLength);
    const videoContainer = document.getElementById(videoContainerId);

    function checkVolume() {
        if (!videoContainer) return;
        analyser.getByteFrequencyData(dataArray);
        let sum = dataArray.reduce((a, b) => a + b, 0);
        if (stream.getAudioTracks()[0]?.enabled && sum / bufferLength > SPEAKING_THRESHOLD) {
            videoContainer.classList.add('speaking');
        } else {
            videoContainer.classList.remove('speaking');
        }
        requestAnimationFrame(checkVolume);
    }
    requestAnimationFrame(checkVolume);
}

function createVideoPlayer(id, name, stream, isMuted = false, audioEnabled = true) {
    const container = document.createElement("div");
    container.id = id;
    container.className = "video-player-container";
    
    const video = document.createElement("video");
    video.autoplay = true;
    video.playsInline = true;
    video.muted = isMuted;
    video.srcObject = stream;

    const nameTag = document.createElement("div");
    nameTag.className = "participant-name";
    nameTag.textContent = name;

    const micIcon = document.createElement("div");
    micIcon.className = "mic-icon";
    micIcon.innerHTML = `<i class="fas fa-microphone"></i>`;
    if (!audioEnabled) {
        micIcon.classList.add("muted");
        micIcon.querySelector("i").className = "fas fa-microphone-slash";
    }

    container.appendChild(video);
    container.appendChild(nameTag);
    container.appendChild(micIcon);
    videosDiv.appendChild(container);
}

function setLocalStream(stream) {
    console.log("Setting local stream"); // Add logging
    localStream = stream;
    let localVideoContainer = document.getElementById("localVideoContainer");
    if (!localVideoContainer) {
        const audioEnabled = stream.getAudioTracks()[0]?.enabled ?? true;
        console.log("Creating local video player"); // Add logging
        createVideoPlayer("localVideoContainer", `${myName} (You)`, stream, true, audioEnabled);
    } else {
        console.log("Updating local video player"); // Add logging
        localVideoContainer.querySelector("video").srcObject = stream;
    }

    for (const remoteId in pcs) {
        const pc = pcs[remoteId];
        stream.getTracks().forEach(track => {
            const sender = pc.getSenders().find(s => s.track && s.track.kind === track.kind);
            if (sender) sender.replaceTrack(track).catch(e => console.error("Replace track failed:", e));
        });
    }
}

function createPeerConnection(remoteId, remoteName, initialAudioState) {
    console.log("Setting up peer connection for:", remoteId); // Add logging
    const pc = new RTCPeerConnection({
        iceServers: [
            { urls: 'stun:stun.l.google.com:19302' },
            { urls: 'stun:stun1.l.google.com:19302' }
        ]
    });
    pcs[remoteId] = pc;

    localStream.getTracks().forEach(track => {
        console.log("Adding local track to peer connection:", track.kind); // Add logging
        pc.addTrack(track, localStream);
    });

    pc.ontrack = (event) => {
        console.log("Received remote track:", event.track.kind); // Add logging
        const remoteStream = event.streams[0];
        const containerId = `remoteContainer-${remoteId}`;
        let remoteContainer = document.getElementById(containerId);
        if (!remoteContainer) {
            console.log("Creating new video player for:", remoteName); // Add logging
            createVideoPlayer(containerId, remoteName, remoteStream, false, initialAudioState);
        } else {
            console.log("Updating existing video player for:", remoteName); // Add logging
            remoteContainer.querySelector("video").srcObject = remoteStream;
        }
        monitorAudioLevel(remoteStream, containerId);
    };

    pc.onicecandidate = (event) => {
        if (event.candidate && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: "candidate", candidate: event.candidate, from: myId, to: remoteId }));
        }
    };

    return pc;
}

async function joinCall(room, name) {
    myName = name;
    setupDiv.classList.add("hidden");
    roomDiv.classList.remove("hidden");

    sessionStorage.setItem('room', room);
    sessionStorage.setItem('name', name);

    try {
        const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
        cameraStream = stream;

        // --- NEW: Apply saved media states after getting the stream ---
        const savedMicMuted = sessionStorage.getItem('micMuted') === 'true';
        const savedCameraOff = sessionStorage.getItem('cameraOff') === 'true';

        const audioTrack = stream.getAudioTracks()[0];
        if (audioTrack && savedMicMuted) {
            audioTrack.enabled = false;
            // Update UI
            muteBtn.classList.add("toggled");
            muteBtn.querySelector("i").className = 'fas fa-microphone-slash';
            muteBtn.querySelector("span").textContent = 'Unmute';
        }

        const videoTrack = stream.getVideoTracks()[0];
        if (videoTrack && savedCameraOff) {
            videoTrack.enabled = false;
            // Update UI
            cameraBtn.classList.add("toggled");
            cameraBtn.querySelector("i").className = 'fas fa-video-slash';
            cameraBtn.querySelector("span").textContent = 'Cam On';
        }
        // --- END NEW SECTION ---

        setLocalStream(cameraStream);
        monitorAudioLevel(cameraStream, "localVideoContainer");
    } catch (error) {
        console.error("Error accessing media devices.", error);
        return;
    }

    ws = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws/${room}`);

    ws.onopen = () => {
        const audioEnabled = localStream.getAudioTracks()[0]?.enabled ?? true;
        ws.send(JSON.stringify({ type: "join", from: myId, name: myName, audioEnabled }));
    };

    ws.onmessage = async (event) => {
        const msg = JSON.parse(event.data);
        if (msg.from === myId) return;
        
        console.log("Received message:", msg.type, "from:", msg.from); // Add logging

        let pc = pcs[msg.from];
        if (!pc && (msg.type === "offer" || msg.type === "join")) {
            console.log("Creating new peer connection for:", msg.from); // Add logging
            pc = createPeerConnection(msg.from, msg.name, msg.audioEnabled);
        }

        switch (msg.type) {
            case "join":
                const offer = await pc.createOffer();
                await pc.setLocalDescription(offer);
                const joinAudioEnabled = localStream.getAudioTracks()[0]?.enabled ?? true;
                ws.send(JSON.stringify({ ...pc.localDescription.toJSON(), from: myId, to: msg.from, name: myName, audioEnabled: joinAudioEnabled }));
                break;
            case "offer":
                await pc.setRemoteDescription(new RTCSessionDescription(msg));
                const answer = await pc.createAnswer();
                await pc.setLocalDescription(answer);
                const offerAudioEnabled = localStream.getAudioTracks()[0]?.enabled ?? true;
                ws.send(JSON.stringify({ ...pc.localDescription.toJSON(), from: myId, to: msg.from, name: myName, audioEnabled: offerAudioEnabled }));
                break;
            case "answer":
                await pc.setRemoteDescription(new RTCSessionDescription(msg));
                break;
            case "candidate":
                if (pc) await pc.addIceCandidate(new RTCIceCandidate(msg.candidate));
                break;
            case "audio-toggle":
                const remoteContainer = document.getElementById(`remoteContainer-${msg.from}`);
                if (remoteContainer) {
                    const micIcon = remoteContainer.querySelector('.mic-icon');
                    micIcon.classList.toggle("muted", !msg.enabled);
                    micIcon.querySelector("i").className = `fas ${msg.enabled ? 'fa-microphone' : 'fa-microphone-slash'}`;
                }
                break;
            case "user-left":
                if (pcs[msg.id]) {
                    pcs[msg.id].close();
                    delete pcs[msg.id];
                    document.getElementById(`remoteContainer-${msg.id}`)?.remove();
                }
                break;
        }
    };
}

joinBtn.onclick = () => {
    const room = roomInput.value.trim() || "default-room";
    const name = nameInput.value.trim() || "Guest";
    joinCall(room, name);
};

// --- MODIFIED: Save state on click ---
muteBtn.onclick = () => {
    const audioTrack = localStream.getAudioTracks()[0];
    if (audioTrack) {
        audioTrack.enabled = !audioTrack.enabled;
        const isMuted = !audioTrack.enabled;
        
        sessionStorage.setItem('micMuted', isMuted); // Save state
        
        muteBtn.classList.toggle("toggled", isMuted);
        muteBtn.querySelector("i").className = `fas ${isMuted ? 'fa-microphone-slash' : 'fa-microphone'}`;
        muteBtn.querySelector("span").textContent = isMuted ? 'Unmute' : 'Mute';

        const localMicIcon = document.getElementById("localVideoContainer")?.querySelector('.mic-icon');
        if (localMicIcon) {
            localMicIcon.classList.toggle("muted", isMuted);
            localMicIcon.querySelector("i").className = `fas ${isMuted ? 'fa-microphone-slash' : 'fa-microphone'}`;
        }
        
        ws.send(JSON.stringify({ type: "audio-toggle", from: myId, enabled: audioTrack.enabled }));
    }
};

// --- MODIFIED: Save state on click ---
cameraBtn.onclick = () => {
    const videoTrack = localStream.getVideoTracks()[0];
    if (videoTrack) {
        videoTrack.enabled = !videoTrack.enabled;
        const isOff = !videoTrack.enabled;

        sessionStorage.setItem('cameraOff', isOff); // Save state

        cameraBtn.classList.toggle("toggled", isOff);
        cameraBtn.querySelector("i").className = `fas ${isOff ? 'fa-video-slash' : 'fa-video'}`;
        cameraBtn.querySelector("span").textContent = isOff ? 'Cam On' : 'Cam Off';
    }
};

shareScreenBtn.onclick = async () => {
    try {
        const screenStream = await navigator.mediaDevices.getDisplayMedia({ video: true, audio: true });
        setLocalStream(screenStream);
        monitorAudioLevel(screenStream, "localVideoContainer");
        screenStream.getVideoTracks()[0].onended = () => {
            setLocalStream(cameraStream);
            monitorAudioLevel(cameraStream, "localVideoContainer");
        };
    } catch (err) {
        setLocalStream(cameraStream);
        monitorAudioLevel(cameraStream, "localVideoContainer");
    }
};

// --- MODIFIED: Clear all session data ---
endBtn.onclick = () => {
    sessionStorage.clear(); // Clear all session data

    Object.values(pcs).forEach(pc => pc.close());
    if (ws) ws.close();
    if (localStream) localStream.getTracks().forEach(track => track.stop());
    if (audioContext) audioContext.close().then(() => window.location.reload());
    else window.location.reload();
};

window.addEventListener('beforeunload', (event) => {
    // No confirmation needed as we have auto-rejoin
});

window.addEventListener('load', () => {
    const savedRoom = sessionStorage.getItem('room');
    const savedName = sessionStorage.getItem('name');
    if (savedRoom && savedName) {
        joinCall(savedRoom, savedName);
    }
});