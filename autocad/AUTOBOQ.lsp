;; AUTOBOQ.lsp - Kich hoat MEP-Agents Swarm AI tu AutoCAD.
;;
;; Truoc day duong dan toi autoboq.py bi hardcode theo may ca nhan
;; ("C:\\Users\\liend\\MEP-Agents\\..."), nen lenh chi chay dung tren dung 1 may.
;; Nay doc duong dan goc du an tu bien moi truong MEP_AGENTS_HOME (dat san tren
;; may tram khi cai dat), roi moi roi ve thu tim canh vi tri file .lsp nay dang
;; duoc load (findfile), de khong con phu thuoc ten user Windows co dinh.
(defun c:AUTOBOQ ()
  (setq mep-home (getenv "MEP_AGENTS_HOME"))

  (if (or (null mep-home) (= mep-home ""))
    (progn
      ;; findfile chi tim duoc file trong support path cua AutoCAD, nhung
      ;; thu de ho tro truong hop nguoi dung da them thu muc autocad/ vao do.
      (setq lsp-path (findfile "AUTOBOQ.lsp"))
      (if lsp-path
        (setq mep-home (vl-filename-directory (vl-filename-directory lsp-path)))
      )
    )
  )

  (if (or (null mep-home) (= mep-home ""))
    (progn
      (princ "\n[MEP-Agents] Chua tim thay duong dan cai dat.")
      (princ "\nHay dat bien moi truong MEP_AGENTS_HOME tro toi thu muc goc du an")
      (princ "\n(vi du: C:\\Users\\<ten-ban>\\MEP-Agents) roi khoi dong lai AutoCAD.")
      (princ)
    )
    (progn
      (princ "\nDang kich hoat MEP-Agents Swarm AI...")
      (setq script-path (strcat mep-home "\\autocad\\autoboq.py"))
      ;; Chay script Python qua shell (gia dinh dang dung uv run cho moi truong ao)
      (command "start" "uv" "run" "python" script-path)
      (princ "\nDa gui du lieu ban ve hien tai len May chu AI (FastAPI). Vui long xem ket qua tren Web!")
      (princ)
    )
  )
)
