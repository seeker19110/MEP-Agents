import React, { useState, useEffect } from 'react';
import { UploadCloud, File, CheckCircle, Activity, Box, DownloadCloud } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import axios from 'axios';

// Trước đây hardcode thẳng localhost:8083 — build production trỏ server khác phải sửa
// code rồi build lại (cùng vấn đề đã sửa ở plugin Revit/AutoCAD, xem TECH_DEBT.md mục 8).
// Nay đọc qua biến môi trường Vite (`.env`/`.env.production`, tiền tố bắt buộc `VITE_`),
// không đặt thì rơi về localhost mặc định cho dev.
const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8083';
const API_URL = `${API_BASE}/api/v1`;
const WS_BASE = import.meta.env.VITE_WS_BASE || API_BASE.replace(/^http/, 'ws');
const WS_URL = `${WS_BASE}/ws`;
// Chỉ cần đặt khi server bật MEP_AGENTS_API_KEY (xem TECH_DEBT.md mục 7) — để trống thì
// server vẫn mở như trước (mặc định dev cục bộ).
const API_KEY = import.meta.env.VITE_API_KEY || '';
const authHeaders = API_KEY ? { 'X-API-Key': API_KEY } : {};

function App() {
  const [file, setFile] = useState(null);
  const [isUploading, setIsUploading] = useState(false);
  const [taskId, setTaskId] = useState(null);
  const [logs, setLogs] = useState([]);
  const [taskStatus, setTaskStatus] = useState('');

  const handleDrop = (e) => {
    e.preventDefault();
    const droppedFile = e.dataTransfer.files[0];
    if (droppedFile && (droppedFile.name.endsWith('.dwg') || droppedFile.name.endsWith('.dxf'))) {
      setFile(droppedFile);
    }
  };

  const handleUpload = async () => {
    if (!file) return;
    setIsUploading(true);
    setLogs(["Đang tải file lên máy chủ FastAPI..."]);
    
    const formData = new FormData();
    formData.append("file", file);

    try {
      const response = await axios.post(`${API_URL}/takeoff`, formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
          ...authHeaders,
        }
      });
      setTaskId(response.data.task_id);
      setLogs(prev => [...prev, "Tải lên thành công! Bắt đầu hàng đợi Celery..."]);
    } catch (error) {
      setLogs(prev => [...prev, `Lỗi tải lên: ${error.message}`]);
      setIsUploading(false);
    }
  };

  // Trước đây dùng setInterval polling HTTP mỗi 1.5s (tốn round-trip + độ trễ tới 1.5s).
  // Nay mở 1 kết nối WebSocket duy nhất tới `/ws/task/{taskId}` (src/api.py), server chỉ
  // đẩy dữ liệu khi trạng thái thay đổi thật và tự đóng kết nối khi tác vụ xong.
  useEffect(() => {
    if (!taskId || taskStatus === 'success') return undefined;

    const wsQuery = API_KEY ? `?api_key=${encodeURIComponent(API_KEY)}` : '';
    const ws = new WebSocket(`${WS_URL}/task/${taskId}${wsQuery}`);

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      setTaskStatus(data.status);

      if (data.logs) {
        setLogs(prev => {
          const newLogs = [...prev];
          data.logs.forEach(l => {
            if (!newLogs.includes(l)) newLogs.push(l);
          });
          return newLogs;
        });
      }

      if (data.status === 'success') {
        setIsUploading(false);
        setLogs(prev => [...prev, "✅ Hoàn tất! Bảng BOQ đã sẵn sàng."]);
      } else if (data.status === 'error') {
        setIsUploading(false);
      }
    };

    ws.onerror = () => {
      console.error("WebSocket lỗi kết nối tới máy chủ trạng thái tác vụ.");
    };

    return () => ws.close();
  }, [taskId, taskStatus]);

  const handleDownload = () => {
    if (taskId) {
      const query = API_KEY ? `?api_key=${encodeURIComponent(API_KEY)}` : '';
      window.location.href = `${API_URL}/download/${taskId}${query}`;
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 flex flex-col font-sans text-slate-200 relative overflow-hidden">
      {/* Background Orbs */}
      <div className="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] bg-cyan-600/20 blur-[120px] rounded-full pointer-events-none" />
      <div className="absolute bottom-[-10%] right-[-10%] w-[40%] h-[40%] bg-blue-600/20 blur-[120px] rounded-full pointer-events-none" />

      {/* Header */}
      <header className="glass-panel sticky top-0 z-50 flex items-center justify-between px-8 py-4">
        <div className="flex items-center gap-3">
          <Box className="w-8 h-8 text-cyan-400" />
          <h1 className="text-xl font-bold bg-gradient-to-r from-cyan-400 to-blue-500 bg-clip-text text-transparent">
            MEP-Agents Cloud
          </h1>
        </div>
        <div className="flex items-center gap-4 text-sm font-medium">
          <span className="flex items-center gap-2 text-cyan-400"><Activity className="w-4 h-4"/> Swarm Active</span>
          <img src="https://ui-avatars.com/api/?name=Admin&background=0D8ABC&color=fff" alt="User" className="w-8 h-8 rounded-full border border-white/20" />
        </div>
      </header>

      <main className="flex-1 max-w-6xl w-full mx-auto p-8 grid grid-cols-1 lg:grid-cols-2 gap-8 z-10">
        {/* Left Col: Upload */}
        <div className="flex flex-col gap-6">
          <div className="glass-panel p-8 rounded-2xl">
            <h2 className="text-2xl font-semibold mb-2">Auto Quantity Takeoff</h2>
            <p className="text-slate-400 mb-8">Kéo thả bản vẽ CAD (DWG/DXF) để Bầy đàn AI tự động xử lý.</p>
            
            <div 
              onDragOver={(e) => e.preventDefault()}
              onDrop={handleDrop}
              className={`border-2 border-dashed rounded-xl p-12 flex flex-col items-center justify-center transition-all ${file ? 'border-cyan-500 bg-cyan-500/10' : 'border-slate-700 hover:border-cyan-500/50 hover:bg-slate-800/50'}`}
            >
              {file ? (
                <motion.div initial={{scale:0.9}} animate={{scale:1}} className="flex flex-col items-center gap-4">
                  <File className="w-16 h-16 text-cyan-400" />
                  <span className="font-medium text-lg">{file.name}</span>
                  <button onClick={handleUpload} disabled={isUploading} className="mt-4 px-6 py-2.5 bg-cyan-600 hover:bg-cyan-500 rounded-lg font-semibold transition-colors disabled:opacity-50 flex items-center gap-2">
                    {isUploading ? 'Đang xử lý...' : 'Phân tích bản vẽ'}
                  </button>
                </motion.div>
              ) : (
                <div className="flex flex-col items-center gap-4 text-slate-400">
                  <UploadCloud className="w-16 h-16 opacity-50" />
                  <span className="font-medium">Kéo thả file CAD vào đây</span>
                  <span className="text-sm">hoặc click để chọn file</span>
                </div>
              )}
            </div>
          </div>

          <AnimatePresence>
            {taskStatus === 'success' && (
              <motion.div initial={{opacity:0, y:20}} animate={{opacity:1, y:0}} className="glass-panel p-6 rounded-2xl flex items-center justify-between border-emerald-500/30 bg-emerald-950/20">
                <div className="flex items-center gap-3">
                  <CheckCircle className="w-6 h-6 text-emerald-400" />
                  <div>
                    <h3 className="font-semibold text-emerald-100">Báo cáo BOQ đã hoàn tất</h3>
                    <p className="text-sm text-emerald-400/80">Nhấp để tải file Excel dự toán.</p>
                  </div>
                </div>
                <button onClick={handleDownload} className="px-4 py-2 bg-emerald-600/20 hover:bg-emerald-600/40 text-emerald-400 rounded-lg font-medium transition-colors border border-emerald-500/30 flex items-center gap-2">
                  <DownloadCloud className="w-4 h-4"/> Tải Excel
                </button>
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {/* Right Col: Terminal Console */}
        <div className="glass-panel rounded-2xl p-0 flex flex-col overflow-hidden border-slate-700/50 shadow-[0_0_40px_rgba(6,182,212,0.1)]">
          <div className="bg-slate-900 px-4 py-3 border-b border-white/5 flex items-center gap-2">
            <div className="w-3 h-3 rounded-full bg-rose-500" />
            <div className="w-3 h-3 rounded-full bg-amber-500" />
            <div className="w-3 h-3 rounded-full bg-emerald-500" />
            <span className="ml-2 text-xs font-mono text-slate-500">Agentic Swarm Terminal (LIVE API)</span>
          </div>
          <div className="p-6 font-mono text-sm flex-1 bg-[#0a0f18] text-slate-300 overflow-y-auto space-y-3">
            {logs.length === 0 ? (
              <p className="text-slate-600">Waiting for input...</p>
            ) : (
              <AnimatePresence>
                {logs.map((log, i) => (
                  <motion.div 
                    key={i} 
                    initial={{opacity: 0, x: -10}} 
                    animate={{opacity: 1, x: 0}}
                    className={`flex gap-3 ${log.includes('✅') ? 'text-emerald-400' : ''}`}
                  >
                    <span className="text-slate-600 shrink-0">[{new Date().toLocaleTimeString()}]</span>
                    <span>{log}</span>
                  </motion.div>
                ))}
              </AnimatePresence>
            )}
            {isUploading && (
              <motion.div animate={{opacity:[0.3, 1, 0.3]}} transition={{repeat:Infinity, duration:1.5}} className="flex gap-3 text-cyan-500">
                <span className="text-slate-600 shrink-0">[{new Date().toLocaleTimeString()}]</span>
                <span>Đang lắng nghe WebSocket từ Celery Worker...</span>
              </motion.div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}

export default App;
