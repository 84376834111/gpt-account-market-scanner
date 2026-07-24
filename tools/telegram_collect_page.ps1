$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$OutputEncoding = [Console]::OutputEncoding
Add-Type -AssemblyName UIAutomationClient

$process = Get-Process Telegram | Select-Object -First 1
$root = [System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]$process.MainWindowHandle)
$listType = New-Object System.Windows.Automation.PropertyCondition(
    [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
    [System.Windows.Automation.ControlType]::List
)
$dialogName = [string]([char]0x5BF9) + [char]0x8BDD
$listName = New-Object System.Windows.Automation.PropertyCondition(
    [System.Windows.Automation.AutomationElement]::NameProperty,
    $dialogName
)
$listCondition = New-Object System.Windows.Automation.AndCondition($listType, $listName)
$list = $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $listCondition)
if ($null -eq $list) {
    throw "Telegram search results list not found"
}

$itemCondition = New-Object System.Windows.Automation.PropertyCondition(
    [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
    [System.Windows.Automation.ControlType]::ListItem
)
$items = $list.FindAll([System.Windows.Automation.TreeScope]::Descendants, $itemCondition)
$urls = @()
$names = @()
foreach ($item in $items) {
    $name = $item.Current.Name
    $names += $name
    $matches = [regex]::Matches(
        $name,
        "https?://(?:pay\.ldxp\.cn|(?:www\.)?catfk\.com)/(?:shop|item)/[A-Za-z0-9._-]+"
    )
    $urls += $matches | ForEach-Object { $_.Value.TrimEnd(".") }
}

$fingerprintSource = if ($names.Count -gt 0) {
    "$($names.Count)|$($names[0])|$($names[-1])"
} else {
    "empty"
}
$sha = [System.Security.Cryptography.SHA256]::Create()
$fingerprint = [BitConverter]::ToString(
    $sha.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($fingerprintSource))
).Replace("-", "").ToLowerInvariant()

[PSCustomObject]@{
    item_count = $items.Count
    fingerprint = $fingerprint
    urls = @($urls | Sort-Object -Unique)
} | ConvertTo-Json -Depth 4 -Compress
