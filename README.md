# onno-x

CLI coding agent open-source dengan dukungan multi-model dan fungsionalitas setara **Claude Code CLI**:
- **Model Fleksibel**: Local LLM (Hermes, Llama, Qwen via Ollama/vLLM/llama.cpp/LM Studio) & Remote API (Claude 3.5 Sonnet, GPT-4o, Groq, dll).
- **Autonomous Tool Execution**: 12 Tools otonom (Read, Write, Edit exact replacement, Delete, Grep code search, List dir, Shell execution, Web fetch, Web search, Skill search & load, serta Interactive User Follow-up Question `ask_user`).
- **Live Streaming Tokens**: Output token mengalir secara real-time ke terminal dengan interupsi halus `Ctrl+C`.
- **Disk-Level Undo/Rewind**: Perintah `/rewind` atau `/undo` tidak hanya memulihkan context dialog tetapi juga memulihkan file fisik di disk yang diubah/dibuat.
- **3-Mode Permissions**: Mode perizinan granular (`auto`, `manual`, `all`/YOLO) dengan shortcut cepat `[y/N/a]` untuk menerima seluruh perintah dalam satu sesi.
- **Claude Code Slash Commands**: Mendukung menu perintah garis miring `/` yang identik dengan dokumentasi resmi Claude Code (`menu.md`).

---

## 🚀 Instalasi Global

```bash
cd /Users/mac/files/onno-x
pip3 install -e .

# Pasang alias global ke shell agar bisa dibuka di mana saja:
echo "alias onno-x='/Users/mac/files/onno-x/.venv/bin/onno-x'" >> ~/.zshrc
source ~/.zshrc
```

---

## ⚡ Menu Perintah Garis Miring (Slash Commands)

Ketik `/` pada prompt `onno-x ❯ ` untuk membuka menu dropdown interaktif autocomplete. Semua perintah berikut telah disamakan fungsinya dengan Claude Code (`menu.md`):

| Perintah | Fungsi |
|---|---|
| `/help` | Menampilkan tabel seluruh slash commands |
| `/plan [on\|off]` | Mode perancangan arsitektur sebelum coding (Plan Mode) |
| `/context [all]` | Menampilkan rincian pemakaian token & pesan di context window |
| `/compact` | Merangkum percakapan untuk menghemat context window |
| `/cost` / `/usage` / `/stats` | Statistik jumlah token masuk/keluar & estimasi biaya sesi |
| `/doctor` / `/checkup` | Diagnostik kesehatan model, network latency, git repo, & tools |
| `/add-dir <path>` | Menambahkan akses direktori tambahan ke sesi |
| `/cd <path>` | Berpindah direktori kerja tanpa menghapus percakapan |
| `/diff` | Melihat perubahan git diff pada working tree |
| `/commit [msg]` | Menganalisis git diff dan membuat conventional commit otomatis |
| `/pr [title]` | Merangkum perubahan dan membuat Pull Request via GitHub CLI (`gh`) |
| `/code-review` / `/review` | Meninjau kode / git diff untuk mencari bug & kerentanan |
| `/security-review` | Meninjau kode terhadap celah keamanan (OWASP, injection, leak) |
| `/simplify` | Menyederhanakan struktur kode & membuang duplikasi |
| `/permissions [auto\|manual\|all]` | Mengatur izin tools (Auto: konfirmasi shell/delete, Manual: konfirmasi semua tulis/shell, All: terima semua/YOLO) |
| `/mcp [list\|reload]` | Mengelola koneksi Model Context Protocol server eksternal (`.mcp.json`) |
| `/save` | Menyimpan sesi percakapan aktif secara eksplisit ke disk |
| `/sessions` / `/history` | Menampilkan riwayat seluruh sesi percakapan yang tersimpan di disk |
| `/resume [id]` | Melanjutkan kembali sesi sebelumnya dari disk (default: sesi terakhir) |
| `/autoresume [on\|off]` | Mengaktifkan/menonaktifkan auto-resume otomatis saat onno-x dibuka |
| `/steps <n>` | Mengatur batas langkah otonom (*max steps*) per giliran (default: 50–100) |
| `/mode [auto\|all\|manual]` | Mengatur mode perizinan eksekusi tool & bash (`Shift+Tab` untuk siklus cepat) |
| `/notify [on\|off]` | Mengaktifkan/menonaktifkan peringatan suara (terminal bell) saat turn selesai |
| `/run [cmd]` | Menjalankan test / verifikasi runtime aplikasi |
| `/verify` | Memverifikasi hasil pekerjaan end-to-end |
| `/branch [name]` | Membuat checkpoint cabang percakapan |
| `/rewind` / `/undo` | Mengembalikan percakapan & memulihkan file fisik di disk ke kondisi checkpoint sebelumnya |
| `/btw <pertanyaan>` | Pertanyaan sampingan tanpa mencemari riwayat konteks utama |
| `/copy` | Menyalin jawaban terakhir ke clipboard terminal |
| `/export [file]` | Mengekspor riwayat percakapan ke file markdown |
| `/config` / `/settings` | Melihat & mengubah parameter konfigurasi model |
| `/model <alias>` | Mengganti model aktif saat sesi berjalan |
| `/models` | Melihat daftar semua model lokal & cloud |
| `/effort [low\|med\|high]` | Mengatur tingkat reasoning / temperature model |
| `/fast [on\|off]` | Mengaktifkan mode cepat (temp=0.0 deterministik) |
| `/output-style [style]` | Mengatur gaya output (`default`, `concise`, `verbose`) |
| `/goal <target>` | Menugaskan agent bekerja hingga target tercapai |
| `/init` | Membuat panduan proyek `ONNO.md` / `CLAUDE.md` |
| `/memory` | Menampilkan instruksi persistent proyek |
| `/skill <name>` | Menjalankan skill panduan tertentu |
| `/skill install <url>` | Memasang skill langsung dari URL GitHub / raw |
| `/skills [query]` | Menampilkan & memfilter seluruh skill terpasang |
| `/clear` / `/reset` | Membersihkan layar & mereset context percakapan |
| `/exit` / `/quit` | Keluar dari sesi interaktif |

---

## 🛠️ Manajemen Model (`onno-x model`)

```bash
# Tambah model lokal
onno-x model add onno --provider openai --id onno-ai --url http://192.168.100.105:8083 --key "" --temp 0.0

# Tambah model cloud Anthropic / OpenAI
onno-x model add claude --provider anthropic --id claude-3-5-sonnet-20241022 --key sk-ant-...
onno-x model add gpt4o --provider openai --id gpt-4o --key sk-...

# Ganti model aktif
onno-x model use onno
```

---

## ⚡ Manajemen Skills & Plugin Marketplace (`/plugin`)

`onno-x` mendukung sistem plugin dan marketplace layaknya Claude Code:

```text
# 1. Tambah marketplace repo baru
onno-x ❯ /plugin marketplace add DietrichGebert/ponytail

# 2. Pasang plugin / skill dari marketplace
onno-x ❯ /plugin install ponytail@DietrichGebert/ponytail
# atau langsung:
onno-x ❯ /plugin install DietrichGebert/ponytail

# 3. Lihat daftar marketplace & plugin yang aktif
onno-x ❯ /plugin list

# 4. Hapus plugin
onno-x ❯ /plugin remove ponytail
```

---

## 🛡️ Integrasi Eksternal: MCP Server & Obsidian Memory

### 1. HexStrike AI MCP Server (`kali@192.168.100.102`)
Telah terhubung otomatis melalui konfigurasi `.mcp.json` via SSH tunneling ke API port 8888 (184 security tools: nmap, nuclei, sqlmap, subfinder, ffuf, dirsearch, dll).
Gunakan perintah:
```text
onno-x ❯ /mcp
onno-x ❯ /mcp reload
```

### 2. API Anything Web Extraction MCP (`api-anything`)
Telah terhubung otomatis melalui `.mcp.json` menggunakan Node v24 lokal. Menyediakan tool untuk:
- `find_sites`: Mencari katalog web yang sudah dipetakan menjadi API langsung.
- `call_operation`: Memanggil operasi scraping/data dari situs mana pun langsung via HTTP cepat (tier 1).
- `learn_site`: Mempelajari pola request situs baru di internet secara otomatis.

### 3. Obsidian Long-term Memory (`http://192.168.100.102:2233`)
Terintegrasi langsung ke dalam 3 tool otonom:
- `obsidian_search_notes(query)`: Mencari catatan, temuan bug bounty, dan laporan di Obsidian.
- `obsidian_read_note(note_name)`: Membaca isi lengkap markdown catatan Obsidian.
- `obsidian_write_note(title, content, folder)`: Menyimpan temuan riset baru ke Obsidian Knowledge.
Visualizer graph juga dapat diakses langsung di browser: `http://192.168.100.102:2233/`

Bisa juga menggunakan CLI command:
```bash
# Install skill langsung dari URL GitHub
onno-x skill install https://github.com/DietrichGebert/ponytail
```
onno-x model add onno-x \                          
    --provider openai \
    --id onno-ai \
    --url http://192.168.100.105:8080 \
    --key "" \
    --temp 0 \
    --tokens 60096 \
    --set-active

onno-x model add onnobotai \                          
onno-x model add onnobotai --provider openai --id onnobotai --url http://100.105.127.40:8080/v1 --key "sk-ab8cbfa0e3341508-9jcdim-dcd3869a" --temp 0 --tokens 60000 --set-active

onno-x model add 9router --provider openai --id ag/gemini-3.8-flash-medium --url http://192.168.100.105:20128/v1 --key "sk-ab8cbfa0e3341508-9jcdim-dcd3869a" --temp 0 --tokens 120000 --set-active

onno-x model add free-ai-1 --provider openai --id qwen7b --url http://192.168.100.105:999/v1/chat/completions --key "sk-ab8cbfa0e3341508-9jcdim-dcd3869a" --temp 0 --tokens 120000 --set-active

onno-x model add free-ai-2 --provider openai --id deepseek-r1 --url http://192.168.100.105:999/v1/chat/completions --key "sk-ab8cbfa0e3341508-9jcdim-dcd3869a" --temp 0 --tokens 120000 --set-active

---

## 💾 Manajemen Sesi & Auto-Resume (Persistence)

Onno-X secara otomatis menyimpan seluruh dialog, pemanggilan tools, dan state ke file JSON di `~/.onno-x/sessions/` pada setiap akhir giliran. Anda tidak akan kehilangan konteks bahkan jika terminal tertutup tiba-tiba atau diinterupsi dengan `Ctrl + C`.

### 1. Menyimpan Sesi Secara Manual
```text
onno-x ❯ /save
```
*Mengonfirmasi penyimpanan file sesi ke disk beserta ID unik sesi (contoh: `sess_20261106_002523`).*

### 2. Melihat Riwayat Sesi
```text
onno-x ❯ /sessions
# atau
onno-x ❯ /history
```
*Menampilkan tabel berisi ID sesi, waktu terakhir diupdate, model yang dipakai, jumlah pesan, dan working directory.*

### 3. Melanjutkan Sesi Sebelumnya (Resume)
* **Dari dalam TUI:**
  ```text
  onno-x ❯ /resume              # Melanjutkan sesi paling terakhir
  onno-x ❯ /resume <session_id> # Melanjutkan sesi spesifik berdasarkan ID
  ```
* **Dari Terminal (CLI):**
  ```bash
  onno-x -r                     # Langsung buka TUI dengan sesi terakhir
  onno-x --resume sess_20261106_002523
  ```

### 4. Mode Auto-Resume (Selalu Mengingat Sesi Sebelumnya)
Jika Anda ingin Onno-X **selalu otomatis mengingat dan memuat sesi terakhir** setiap kali aplikasi dibuka tanpa perlu mengetik `-r` atau `/resume`:
```text
onno-x ❯ /autoresume on       # Aktifkan auto-resume
onno-x ❯ /autoresume off      # Matikan (selalu mulai dari sesi baru)
```

---

## ⚙️ Audit Otonom & Pengaturan Langkah (`/steps`)

Untuk tugas-tugas kompleks seperti audit kode repositori, pentest multi-target, atau refactoring besar, Onno-X dapat mengeksekusi puluhan pemanggilan tools secara berturut-turut tanpa berhenti di tengah jalan:
* **Default Step Budget:** **100 langkah** untuk model cloud/router (`9router`), dan **50 langkah** untuk model lokal.
* **Ubah Batas Langkah Kapan Saja:**
  ```text
  onno-x ❯ /steps 100          # Menyetel batas 100 tool calls per giliran
  onno-x ❯ /steps              # Menampilkan batas langkah saat ini
  ```
* **Auto-Synthesis:** Jika batas langkah tercapai, Onno-X tidak akan berhenti diam melainkan otomatis meminta AI untuk merangkum seluruh temuan dan menyusun laporan audit akhir secara lengkap.

---

## 🖥️ Live Animated Status Bar & Anti-Freeze TUI

Status bar di bagian bawah TUI menyajikan feedback visual dinamis setiap 120ms:
* **Rotating Spinner & Moving Pulse:** `⠋ [■■■□□□□□□□]` berputar dan bergerak dinamis membuktikan aplikasi **aktif dan tidak macet (*no freeze*)**.
* **Keterangan Aktivitas Riil:**
  * `🧠 Membaca konteks & berpikir (9router)... (1.4s)`
  * `📖 Membaca: GEMINI.md (2.1s)`
  * `⚙️ Terminal: ls -la && git status (0.8s)`
  * `🔍 Mencari web: cara install docker ubuntu (1.9s)`
  * `⚡ Menulis respons (145 tokens, 38.2 t/s)`
* **Navigasi & Copy Cepat:**
  * **Mouse Drag + `Cmd+C`:** Seleksi dan salin teks langsung dengan mouse (`mouse=False`).
  * **Auto-Clipboard:** Jawaban otomatis tersinkronisasi ke clipboard macOS (`pbcopy`) dan tersimpan di `~/.onno-x/last_response.txt`.
  * **Shortcut:** `Ctrl+Y` atau `/copy` untuk salin manual jawaban terakhir; `PageUp` / `PageDown` untuk menggulir riwayat.
  * **Ganti Mode Cepat:** Tekan `Shift + Tab` untuk berpindah cepat antara mode `AUTO` ⇄ `ALL` ⇄ `MANUAL`.

---

## 🌐 Universal Multi-Engine Web Search

Modul pencarian `web_search` dirancang multi-engine dan 100% bebas blokir internet positif:
1. **Berita Real-Time:** Google News RSS & Bing News RSS untuk memantau berita hari ini dengan tanggal dan sumber akurat.
2. **Dokumentasi & Tutorial:** Bing Web Organic Parser dengan dekode otomatis URL asli untuk mencari panduan teknis (Docker, Linux, programming, docs).
3. **Pengetahuan & Definisi:** Wikipedia API (Indonesia & English) untuk biografi, penemu, dan konsep ilmu komputer.
4. **Keamanan & Kode:** GitHub Repos API dan HackerNews Algolia untuk mencari tool PoC, CVE, dan diskusi developer.
5. **OpenAI Responses Web Search:** Mendukung delegasi `client.responses.create(tools=[{"type": "web_search"}])` jika router/API key OpenAI tersedia.

---


                                  ┌───────────────────────────┐
                                  │          onno-x           │
                                  │   (CLI Coding & Cyber)    │
                                  └─────────────┬─────────────┘
                                                │
         ┌────────────────────────┬─────────────┴─────────────┬────────────────────────┐
         ▼                        ▼                           ▼                        ▼
┌──────────────────┐    ┌──────────────────┐        ┌──────────────────┐     ┌──────────────────┐
│   Native Tools   │    │ Obsidian Memory  │        │  HexStrike MCP   │     │   API-Anything   │
│    (15 Tools)    │    │ (192.168.100.102)│        │ (192.168.100.102)│     │  (Web Scraper)   │
├──────────────────┤    ├──────────────────┤        ├──────────────────┤     ├──────────────────┤
│ • read/write/edit│    │ • search_notes   │        │ • 184 pentest    │     │ • find_sites     │
│ • run_shell      │    │ • read_note      │        │   tools (nmap,   │     │ • call_operation │
│ • grep_search    │    │ • write_note     │        │   sqlmap, etc.)  │     │ • learn_site     │
│ • ask_user       │    │ • 3D graph (2233)│        │ • SSH JSON-RPC   │     │ • Node v24 MCP   │
└──────────────────┘    └──────────────────┘        └──────────────────┘     └──────────────────┘