# Daftar Slash Commands Claude Code

**Referensi diperiksa:** 4 November 2026\
**Sumber utama:** [Dokumentasi resmi Claude Code --
Commands](https://code.claude.com/docs/en/commands)

Dokumen ini merangkum perintah yang dipanggil dengan mengetik `/` di
dalam sesi Claude Code. Perintah yang tersedia pada instalasi tertentu
dapat berbeda menurut versi Claude Code, sistem operasi, paket/akun,
konfigurasi organisasi, plugin, MCP server, serta skills yang dipasang.

## Cara melihat daftar perintah

-   Ketik `/` pada prompt Claude Code untuk membuka daftar perintah.
-   Ketik `/` diikuti beberapa huruf untuk memfilter daftar.
-   Perintah dikenali sebagai slash command ketika ditulis di awal
    pesan.
-   Argumen dalam tanda `<...>` wajib diisi; argumen dalam tanda `[...]`
    bersifat opsional.
-   Selain perintah bawaan, menu `/` dapat menampilkan skills buatan
    sendiri, perintah dari plugin, dan prompt dari MCP server.

## Daftar perintah

Keterangan jenis: - **Bawaan**: fungsi yang disediakan langsung oleh
Claude Code. - **Skill**: workflow berbasis instruksi/prompt yang
disertakan bersama Claude Code. - **Workflow**: workflow dinamis yang
dapat membagi pekerjaan ke beberapa subagent.

  -------------------------------------------------------------------------------------------------------
  Slash command                                           Jenis                   Fungsi
  ------------------------------------------------------- ----------------------- -----------------------
  `/add-dir <path>`                                       Bawaan                  Menambahkan direktori
                                                                                  lain agar dapat diakses
                                                                                  Claude Code selama
                                                                                  sesi.

  `/advisor [model\|off]`                                 Bawaan                  Mengaktifkan,
                                                                                  menonaktifkan, atau
                                                                                  memilih model penasihat
                                                                                  tambahan.

  `/agents`                                               Bawaan                  Menampilkan panduan
                                                                                  untuk membuat dan
                                                                                  mengelola subagent.

  `/artifact-capabilities`                                Skill                   Memuat referensi
                                                                                  kemampuan artifact,
                                                                                  misalnya konektor dan
                                                                                  unduhan file. Tersedia
                                                                                  pada lingkungan yang
                                                                                  mendukung artifacts.

  `/artifact-diagramming`                                 Skill                   Memuat panduan
                                                                                  pembuatan diagram untuk
                                                                                  artifacts.

  `/artifacts`                                            Bawaan                  Melihat dan membuka
                                                                                  artifacts yang dimiliki
                                                                                  atau dibagikan kepada
                                                                                  pengguna.

  `/auto-mode-setup`                                      Bawaan                  Menyusun rancangan
                                                                                  konfigurasi lingkungan
                                                                                  untuk Auto Mode.
                                                                                  Ketersediaan bergantung
                                                                                  pada versi dan paket.

  `/autocompact [auto\|<tokens>]`                         Bawaan                  Mengatur batas
                                                                                  penggunaan context
                                                                                  sebelum Claude
                                                                                  melakukan compact
                                                                                  otomatis.

  `/autofix-pr [prompt]`                                  Bawaan                  Menjalankan cloud
                                                                                  session untuk memantau
                                                                                  pull request dan
                                                                                  memperbaiki kegagalan
                                                                                  CI atau komentar
                                                                                  reviewer. Memerlukan
                                                                                  `gh` dan akses cloud
                                                                                  sessions.

  `/background [prompt]`                                  Bawaan                  Melepas sesi menjadi
                                                                                  background agent agar
                                                                                  terminal dapat
                                                                                  digunakan untuk
                                                                                  pekerjaan lain. Alias:
                                                                                  `/bg`.

  `/batch <instruction>`                                  Skill                   Membagi perubahan besar
                                                                                  menjadi beberapa
                                                                                  pekerjaan independen
                                                                                  yang dikerjakan paralel
                                                                                  melalui worktree.

  `/branch [name]`                                        Bawaan                  Membuat cabang
                                                                                  percakapan untuk
                                                                                  mencoba pendekatan lain
                                                                                  tanpa kehilangan
                                                                                  percakapan sebelumnya.

  `/btw [question]`                                       Bawaan                  Mengajukan pertanyaan
                                                                                  sampingan tanpa
                                                                                  menambahkannya ke
                                                                                  riwayat percakapan
                                                                                  utama.

  `/bug [report]`                                         Bawaan                  Mengirim laporan bug
                                                                                  dengan pilihan konteks
                                                                                  percakapan yang akan
                                                                                  disertakan. Alias:
                                                                                  `/share`.

  `/cd <path>`                                            Bawaan                  Memindahkan direktori
                                                                                  kerja sesi tanpa
                                                                                  menghapus percakapan.

  `/chrome`                                               Bawaan                  Mengatur integrasi
                                                                                  Claude in Chrome.

  `/claude-api [subcommand]`                              Skill                   Memuat referensi Claude
                                                                                  API dan Managed Agents;
                                                                                  mendukung beberapa
                                                                                  subcommand seperti
                                                                                  `migrate`, `upgrade`,
                                                                                  dan `prompt-audit`.

  `/claude-in-chrome [task]`                              Skill                   Meminta Claude
                                                                                  melakukan tugas melalui
                                                                                  browser Chrome, jika
                                                                                  integrasi Chrome
                                                                                  tersedia.

  `/clear [name]`                                         Bawaan                  Memulai percakapan baru
                                                                                  dengan context kosong.
                                                                                  Alias: `/reset`,
                                                                                  `/new`.

  `/code-review [level] [options] [target]`               Skill                   Meninjau perubahan kode
                                                                                  atau pull request untuk
                                                                                  menemukan bug dan
                                                                                  masalah correctness.
                                                                                  Mendukung opsi seperti
                                                                                  `--fix` dan
                                                                                  `--comment`. Alias:
                                                                                  `/review`.

  `/color [color\|default]`                               Bawaan                  Mengubah warna prompt
                                                                                  bar sesi.

  `/compact [instructions]`                               Bawaan                  Merangkum percakapan
                                                                                  untuk mengurangi
                                                                                  penggunaan context,
                                                                                  dengan instruksi fokus
                                                                                  opsional.

  `/config [key=value ...]`                               Bawaan                  Membuka atau mengubah
                                                                                  pengaturan Claude Code.
                                                                                  Alias: `/settings`.

  `/context [all]`                                        Bawaan                  Menampilkan pemakaian
                                                                                  context dan bagian yang
                                                                                  paling banyak
                                                                                  menggunakannya.

  `/copy [N]`                                             Bawaan                  Menyalin jawaban Claude
                                                                                  terakhir atau jawaban
                                                                                  ke-N sebelumnya.

  `/cost`                                                 Bawaan                  Alias untuk `/usage`.

  `/dataviz [request]`                                    Skill                   Memuat panduan untuk
                                                                                  membuat grafik,
                                                                                  visualisasi data, dan
                                                                                  dashboard.

  `/debug [description]`                                  Skill                   Mengaktifkan pencatatan
                                                                                  debug sesi dan membantu
                                                                                  menganalisis masalah
                                                                                  runtime.

  `/deep-research <question>`                             Workflow                Melakukan riset dengan
                                                                                  beberapa pencarian web,
                                                                                  memeriksa silang
                                                                                  sumber, dan menyusun
                                                                                  laporan bersitasi.

  `/design [brief]`                                       Skill                   Membuat rancangan UI,
                                                                                  alur layar, landing
                                                                                  page, atau poster
                                                                                  sebagai Claude Design
                                                                                  artifact. Memerlukan
                                                                                  dukungan artifacts dan
                                                                                  akses terkait.

  `/design consent`                                       Bawaan                  Memberikan izin akses
                                                                                  Claude ke Claude
                                                                                  Design.

  `/design revoke`                                        Bawaan                  Mencabut izin akses
                                                                                  Claude ke Claude
                                                                                  Design.

  `/design-login`                                         Bawaan                  Mengotorisasi akses
                                                                                  design system untuk
                                                                                  `/design-sync`.

  `/design-sync [hint]`                                   Skill                   Mengonversi design
                                                                                  system React dalam
                                                                                  repository agar dapat
                                                                                  digunakan Claude
                                                                                  Design.

  `/desktop`                                              Bawaan                  Melanjutkan sesi saat
                                                                                  ini di aplikasi Claude
                                                                                  Code Desktop. Alias:
                                                                                  `/app`. Memerlukan
                                                                                  sistem dan paket yang
                                                                                  didukung.

  `/diff`                                                 Bawaan                  Menampilkan dan
                                                                                  meninjau perubahan file
                                                                                  pada working tree.

  `/doctor [prompt-audit [path]]`                         Skill                   Mendiagnosis instalasi,
                                                                                  konfigurasi, ekstensi,
                                                                                  dan file `CLAUDE.md`;
                                                                                  dapat mengusulkan
                                                                                  perbaikan. Alias:
                                                                                  `/checkup`.

  `/effort [level\|auto\|status\|ultracode]`              Bawaan                  Mengatur atau memeriksa
                                                                                  tingkat
                                                                                  effort/reasoning model.

  `/exit`                                                 Bawaan                  Keluar dari sesi CLI
                                                                                  atau melepaskan
                                                                                  terminal dari
                                                                                  background session.
                                                                                  Alias: `/quit`.

  `/export [filename]`                                    Bawaan                  Mengekspor percakapan
                                                                                  saat ini menjadi file
                                                                                  teks atau menyalinnya.

  `/fast [on\|off]`                                       Bawaan                  Mengaktifkan atau
                                                                                  menonaktifkan Fast Mode
                                                                                  jika tersedia.

  `/feedback [report]`                                    Bawaan                  Mengirim masukan atau
                                                                                  laporan tentang Claude
                                                                                  Code.

  `/fewer-permission-prompts`                             Skill                   Menganalisis perintah
                                                                                  Bash/MCP yang sering
                                                                                  digunakan dan menyusun
                                                                                  allowlist untuk
                                                                                  mengurangi permintaan
                                                                                  izin.

  `/focus`                                                Bawaan                  Mengaktifkan atau
                                                                                  menonaktifkan tampilan
                                                                                  fokus yang merangkum
                                                                                  prompt, aktivitas tool,
                                                                                  dan jawaban.

  `/fork [prompt]`                                        Bawaan                  Menyalin percakapan ke
                                                                                  background session baru
                                                                                  sambil mempertahankan
                                                                                  sesi saat ini.

  `/goal [condition\|clear]`                              Bawaan                  Menetapkan kondisi
                                                                                  tujuan agar Claude
                                                                                  melanjutkan pekerjaan
                                                                                  sampai tujuan tercapai
                                                                                  atau dihentikan.

  `/heapdump`                                             Bawaan                  Membuat snapshot heap
                                                                                  JavaScript untuk
                                                                                  diagnosis penggunaan
                                                                                  memori. **Tersembunyi
                                                                                  dari menu; ketik nama
                                                                                  lengkap.** Jangan
                                                                                  membagikan file
                                                                                  `.heapsnapshot` karena
                                                                                  dapat berisi percakapan
                                                                                  dan kredensial.

  `/help`                                                 Bawaan                  Menampilkan bantuan dan
                                                                                  perintah yang tersedia.

  `/hooks`                                                Bawaan                  Melihat konfigurasi
                                                                                  hooks.

  `/ide`                                                  Bawaan                  Mengelola integrasi IDE
                                                                                  dan melihat statusnya.

  `/import [codex\|gemini\|cursor] [--dry-run] [--yes]`   Bawaan                  Mengimpor konfigurasi
                                                                                  dari OpenAI Codex,
                                                                                  Gemini CLI, atau
                                                                                  Cursor.

  `/init`                                                 Bawaan                  Membuat panduan awal
                                                                                  project dalam file
                                                                                  `CLAUDE.md`.

  `/insights`                                             Bawaan                  Membuat laporan HTML
                                                                                  tentang pola penggunaan
                                                                                  Claude Code dan sesi
                                                                                  sebelumnya pada mesin
                                                                                  ini.

  `/install-github-app`                                   Bawaan                  Memasang Claude GitHub
                                                                                  App pada repository
                                                                                  GitHub dan, bila
                                                                                  dipilih, menyiapkan
                                                                                  GitHub Actions.

  `/install-slack-app`                                    Bawaan                  Memasang aplikasi
                                                                                  Claude untuk Slack
                                                                                  melalui proses
                                                                                  otorisasi.

  `/keybindings`                                          Bawaan                  Membuka file pengaturan
                                                                                  shortcut keyboard.

  `/list-agents`                                          Bawaan                  Menampilkan subagent,
                                                                                  teammate, dan sesi
                                                                                  Claude Code lain yang
                                                                                  dapat dihubungi. Alias:
                                                                                  `/peers`. Memerlukan
                                                                                  fitur cross-session
                                                                                  messaging.

  `/login`                                                Bawaan                  Masuk ke akun
                                                                                  Anthropic.

  `/logout`                                               Bawaan                  Keluar dari akun
                                                                                  Anthropic.

  `/loop [interval] [prompt]`                             Skill                   Menjalankan prompt
                                                                                  berulang selama sesi
                                                                                  tetap terbuka. Alias:
                                                                                  `/proactive`.

  `/mcp [subcommand]`                                     Bawaan                  Mengelola koneksi MCP
                                                                                  server dan
                                                                                  autentikasinya,
                                                                                  termasuk reconnect,
                                                                                  enable, dan disable.

  `/memory`                                               Bawaan                  Mengedit file
                                                                                  `CLAUDE.md`, mengatur
                                                                                  auto memory, dan
                                                                                  melihat entri memori.

  `/mobile`                                               Bawaan                  Menampilkan QR code
                                                                                  untuk mengunduh
                                                                                  aplikasi Claude mobile.
                                                                                  Alias: `/ios`,
                                                                                  `/android`.

  `/model [model]`                                        Bawaan                  Memilih model AI yang
                                                                                  digunakan.

  `/output-style [style]`                                 Bawaan                  Melihat atau mengganti
                                                                                  gaya keluaran Claude.

  `/passes`                                               Bawaan                  Membagikan akses uji
                                                                                  coba Claude Code jika
                                                                                  akun memenuhi syarat.

  `/permissions`                                          Bawaan                  Mengelola izin tool
                                                                                  dengan aturan allow,
                                                                                  ask, dan deny. Alias:
                                                                                  `/allowed-tools`.

  `/plan [description]`                                   Bawaan                  Masuk ke Plan Mode
                                                                                  untuk merencanakan
                                                                                  pekerjaan sebelum
                                                                                  implementasi.

  `/plugin [subcommand]`                                  Bawaan                  Melihat dan mengelola
                                                                                  plugin, termasuk
                                                                                  install, enable,
                                                                                  disable, dan list.

  `/plugin-authoring`                                     Skill                   Memuat panduan untuk
                                                                                  membuat plugin/mod.
                                                                                  Memerlukan versi dan
                                                                                  plugin bawaan yang
                                                                                  mendukung.

  `/powerup`                                              Bawaan                  Mempelajari fitur
                                                                                  Claude Code melalui
                                                                                  tutorial interaktif.

  `/privacy-settings`                                     Bawaan                  Melihat dan mengubah
                                                                                  pengaturan privasi.
                                                                                  Hanya tersedia pada
                                                                                  paket tertentu.

  `/radio`                                                Bawaan                  Membuka Claude FM lo-fi
                                                                                  radio di browser.

  `/rate-limit-options`                                   Bawaan                  Menampilkan opsi ketika
                                                                                  batas penggunaan akun
                                                                                  tercapai, misalnya
                                                                                  menunggu reset atau
                                                                                  menambah usage credits.

  `/recap`                                                Bawaan                  Membuat ringkasan satu
                                                                                  baris dari sesi saat
                                                                                  ini.

  `/release-notes`                                        Bawaan                  Melihat catatan rilis
                                                                                  berdasarkan versi
                                                                                  Claude Code.

  `/reload-plugins [--force]`                             Bawaan                  Memuat ulang plugin
                                                                                  aktif agar perubahan
                                                                                  diterapkan tanpa
                                                                                  memulai ulang sesi.

  `/reload-skills`                                        Bawaan                  Memindai ulang
                                                                                  direktori skills dan
                                                                                  custom commands agar
                                                                                  perubahan tersedia di
                                                                                  sesi saat ini.

  `/remote-control`                                       Bawaan                  Membuat sesi lokal
                                                                                  dapat diakses melalui
                                                                                  Remote Control dari
                                                                                  claude.ai. Alias:
                                                                                  `/rc`.

  `/remote-env`                                           Bawaan                  Memilih cloud
                                                                                  environment default
                                                                                  untuk cloud sessions
                                                                                  yang dijalankan dari
                                                                                  CLI.

  `/rename [name]`                                        Bawaan                  Mengganti nama sesi
                                                                                  saat ini.

  `/restart`                                              Bawaan                  Memulai ulang Claude
                                                                                  Code dan melanjutkan
                                                                                  sesi, biasanya untuk
                                                                                  menerapkan update.
                                                                                  Memerlukan kondisi
                                                                                  versi dan platform
                                                                                  tertentu. Alias:
                                                                                  `/update`.

  `/resume [session]`                                     Bawaan                  Melanjutkan percakapan
                                                                                  sebelumnya berdasarkan
                                                                                  ID atau nama sesi.
                                                                                  Alias: `/continue`.

  `/review [level] [options] [target]`                    Skill                   Alias dari
                                                                                  `/code-review` untuk
                                                                                  meninjau perubahan kode
                                                                                  atau pull request.

  `/rewind`                                               Bawaan                  Mengembalikan
                                                                                  percakapan dan/atau
                                                                                  perubahan kode ke
                                                                                  checkpoint sebelumnya.
                                                                                  Alias: `/checkpoint`,
                                                                                  `/undo`.

  `/run`                                                  Skill                   Menjalankan aplikasi
                                                                                  project dan memeriksa
                                                                                  hasil perubahan secara
                                                                                  langsung.

  `/run-skill-generator`                                  Skill                   Membuat instruksi
                                                                                  khusus project agar
                                                                                  `/run` dan `/verify`
                                                                                  mengetahui cara build
                                                                                  dan menjalankan
                                                                                  aplikasi.

  `/sandbox`                                              Bawaan                  Mengaktifkan atau
                                                                                  menonaktifkan sandbox
                                                                                  mode pada platform yang
                                                                                  didukung.

  `/schedule [description]`                               Bawaan                  Membuat, mengubah,
                                                                                  melihat, atau
                                                                                  menjalankan cloud
                                                                                  scheduled tasks. Alias:
                                                                                  `/routines`.

  `/scroll-speed`                                         Bawaan                  Mengatur kecepatan
                                                                                  scroll mouse pada
                                                                                  tampilan terminal
                                                                                  fullscreen yang
                                                                                  didukung.

  `/security-review`                                      Bawaan                  Menganalisis perubahan
                                                                                  branch untuk menemukan
                                                                                  potensi kerentanan
                                                                                  keamanan.

  `/setup-bedrock`                                        Bawaan                  Mengatur autentikasi
                                                                                  dan konfigurasi Amazon
                                                                                  Bedrock. Tersembunyi
                                                                                  sampai konfigurasi
                                                                                  Bedrock terkait
                                                                                  diaktifkan.

  `/setup-vertex`                                         Bawaan                  Mengatur autentikasi
                                                                                  dan konfigurasi Google
                                                                                  Cloud Vertex AI/Agent
                                                                                  Platform. Tersembunyi
                                                                                  sampai konfigurasi
                                                                                  terkait diaktifkan.

  `/simplify [target]`                                    Skill                   Meninjau kode yang
                                                                                  berubah untuk
                                                                                  menyederhanakan
                                                                                  struktur, meningkatkan
                                                                                  penggunaan ulang, dan
                                                                                  efisiensi.

  `/skill-doctor`                                         Bawaan                  Menampilkan penggunaan
                                                                                  context dan frekuensi
                                                                                  pemakaian skills untuk
                                                                                  membantu menemukan
                                                                                  skills yang tidak
                                                                                  diperlukan.

  `/skills`                                               Bawaan                  Menampilkan dan
                                                                                  mengelola daftar skills
                                                                                  serta visibilitasnya
                                                                                  pada menu `/`.

  `/slides [brief]`                                       Skill                   Membuat presentasi
                                                                                  sebagai Claude Slides
                                                                                  artifact. Memerlukan
                                                                                  dukungan artifacts dan
                                                                                  akses template.

  `/stats`                                                Bawaan                  Alias `/usage`, membuka
                                                                                  tab statistik.

  `/status`                                               Bawaan                  Menampilkan status
                                                                                  sesi, versi, model,
                                                                                  akun, dan konektivitas.

  `/statusline`                                           Bawaan                  Mengatur status line
                                                                                  yang tampil pada
                                                                                  terminal.

  `/stickers`                                             Bawaan                  Membuka informasi
                                                                                  pemesanan stiker Claude
                                                                                  Code.

  `/stop`                                                 Bawaan                  Menghentikan background
                                                                                  session yang sedang
                                                                                  diikuti tanpa menghapus
                                                                                  transcript atau
                                                                                  worktree.

  `/subtask <task>`                                       Bawaan                  Menjalankan tugas
                                                                                  sampingan melalui
                                                                                  forked subagent dan
                                                                                  mengembalikan hasilnya
                                                                                  ke percakapan utama.

  `/tasks`                                                Bawaan                  Melihat dan mengelola
                                                                                  pekerjaan background,
                                                                                  termasuk subagent.
                                                                                  Alias: `/bashes`.

  `/team-onboarding`                                      Bawaan                  Membuat panduan
                                                                                  onboarding tim
                                                                                  berdasarkan riwayat
                                                                                  penggunaan Claude Code.

  `/teleport`                                             Bawaan                  Memindahkan cloud
                                                                                  session ke terminal
                                                                                  lokal. Alias: `/tp`.

  `/terminal-setup`                                       Bawaan                  Memasang atau mengatur
                                                                                  shortcut terminal untuk
                                                                                  input baris baru dan
                                                                                  fungsi terminal
                                                                                  lainnya.

  `/theme`                                                Bawaan                  Mengganti tema warna
                                                                                  terminal Claude Code.

  `/tui [default\|fullscreen]`                            Bawaan                  Mengatur renderer
                                                                                  antarmuka terminal dan
                                                                                  memulai ulang tampilan
                                                                                  sesi.

  `/ultrareview [PR or branch]`                           Bawaan                  Menjalankan code review
                                                                                  mendalam dengan
                                                                                  beberapa agent di
                                                                                  cloud. Alternatif yang
                                                                                  disarankan:
                                                                                  `/code-review ultra`.

  `/update-config [request]`                              Skill                   Meminta Claude mengubah
                                                                                  file `settings.json`,
                                                                                  misalnya menambahkan
                                                                                  hook atau mengubah
                                                                                  izin.

  `/upgrade`                                              Bawaan                  Membuka halaman upgrade
                                                                                  paket akun jika
                                                                                  tersedia.

  `/usage`                                                Bawaan                  Menampilkan biaya sesi,
                                                                                  batas penggunaan paket,
                                                                                  dan statistik
                                                                                  aktivitas. Alias:
                                                                                  `/cost`, `/stats`.

  `/usage-credits`                                        Bawaan                  Mengelola atau meminta
                                                                                  usage credits ketika
                                                                                  batas penggunaan
                                                                                  tercapai.

  `/verify`                                               Skill                   Memverifikasi perubahan
                                                                                  dengan membangun,
                                                                                  menjalankan, dan
                                                                                  mengamati aplikasi,
                                                                                  bukan hanya
                                                                                  mengandalkan test atau
                                                                                  type check.

  `/voice [hold\|tap\|off]`                               Bawaan                  Mengatur fitur voice
                                                                                  dictation jika akun
                                                                                  mendukungnya.

  `/web-setup`                                            Bawaan                  Menghubungkan akun
                                                                                  GitHub untuk cloud
                                                                                  sessions menggunakan
                                                                                  kredensial GitHub CLI
                                                                                  lokal.

  `/workflow-authoring`                                   Skill                   Memuat panduan untuk
                                                                                  menulis dynamic
                                                                                  workflows. Hanya
                                                                                  tersedia jika fitur
                                                                                  dynamic workflows
                                                                                  diaktifkan.

  `/workflows`                                            Bawaan                  Membuka tampilan untuk
                                                                                  memantau, menjeda,
                                                                                  melanjutkan, atau
                                                                                  menyimpan workflow.
  -------------------------------------------------------------------------------------------------------

## Perintah lama yang sudah dihapus

Perintah berikut tercantum dalam riwayat dokumentasi, tetapi **bukan
perintah aktif yang sebaiknya digunakan** pada versi saat ini:

  -----------------------------------------------------------------------
  Perintah                            Status / pengganti
  ----------------------------------- -----------------------------------
  `/pr-comments`                      Dihapus pada v2.1.91. Minta Claude
                                      melihat komentar pull request
                                      secara langsung.

  `/ultraplan`                        Dihapus. Gunakan Plan Mode atau
                                      `/plan`.

  `/vim`                              Dihapus pada v2.1.92. Atur Editor
                                      mode melalui `/config`.
  -----------------------------------------------------------------------

## Contoh penggunaan untuk pengembangan aplikasi

  Kebutuhan                                   Perintah yang dapat digunakan
  ------------------------------------------- -------------------------------
  Memulai Claude Code dan mengenali project   `/init`
  Memeriksa aturan project                    `/memory`
  Merencanakan fitur sebelum coding           `/plan`
  Memahami pemakaian context                  `/context`
  Mengurangi context yang sudah panjang       `/compact`
  Memilih model                               `/model`
  Mengatur tingkat effort                     `/effort`
  Mengatur izin akses tool                    `/permissions`
  Menghubungkan database/API melalui MCP      `/mcp`
  Melihat perubahan kode                      `/diff`
  Meninjau kualitas dan bug pada perubahan    `/code-review`
  Memeriksa keamanan perubahan                `/security-review`
  Menyederhanakan kode                        `/simplify`
  Menjalankan aplikasi                        `/run`
  Memverifikasi hasil implementasi            `/verify`
  Mendiagnosis masalah Claude Code            `/doctor`
  Melanjutkan sesi sebelumnya                 `/resume`
  Memulai pekerjaan baru                      `/clear`
  Melihat status dan penggunaan               `/status`, `/usage`

## Catatan penting

1.  Tabel di atas merupakan rangkuman dokumentasi resmi, bukan jaminan
    bahwa semua command tampil pada setiap instalasi.
2.  Perintah **Skill** dan **Workflow** dapat memerlukan versi, fitur,
    paket, atau konfigurasi tertentu.
3.  Skills buatan pengguna dapat membuat slash command sendiri. Pada
    versi baru, custom commands berbasis file telah digabungkan ke
    sistem skills. Contohnya, `.claude/skills/nama-skill/SKILL.md` dapat
    menyediakan perintah `/nama-skill`.
4.  Plugin dapat menambahkan command/skills dengan namespace, sedangkan
    MCP server dapat menambahkan prompt yang tampil seperti command.
5.  Untuk daftar yang benar-benar aktif di perangkat sendiri, buka
    Claude Code lalu ketik `/`. Jika command tidak muncul, periksa
    versi, platform, paket akun, dan konfigurasi yang digunakan.

## Referensi resmi

-   [Commands -- Claude Code
    Documentation](https://code.claude.com/docs/en/commands)
-   [Interactive mode -- Claude Code
    Documentation](https://code.claude.com/docs/en/interactive-mode)
-   [Skills -- Claude Code
    Documentation](https://code.claude.com/docs/en/skills)
-   [CLI reference -- Claude Code
    Documentation](https://docs.anthropic.com/en/docs/claude-code/cli-reference)
