# M2-1 spike — test window จำลอง Godot (fullscreen borderless, สี ET palette)
# เขียน hwnd ลง %TEMP%\et-spike-hwnd.txt แล้วรัน message loop จนถูก kill
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$form = New-Object System.Windows.Forms.Form
$form.FormBorderStyle = 'None'
$form.StartPosition = 'Manual'
$form.Bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
$form.BackColor = [System.Drawing.Color]::FromArgb(7, 5, 15)      # #07050F — ET bg
$form.TopMost = $false
$form.ShowInTaskbar = $false

$label = New-Object System.Windows.Forms.Label
$label.Text = "ET OFFICE - WORKERW SPIKE`n(this should be BEHIND your desktop icons)"
$label.Font = New-Object System.Drawing.Font("Consolas", 28, [System.Drawing.FontStyle]::Bold)
$label.ForeColor = [System.Drawing.Color]::FromArgb(224, 64, 251)  # #E040FB — neon magenta
$label.AutoSize = $false
$label.Dock = 'Fill'
$label.TextAlign = 'MiddleCenter'
$form.Controls.Add($label)

$form.Add_Shown({
    [System.IO.File]::WriteAllText("$env:TEMP\et-spike-hwnd.txt", $form.Handle.ToString())
})

[System.Windows.Forms.Application]::Run($form)
