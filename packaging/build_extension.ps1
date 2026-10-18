# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Ezequiel M. Rezende
<#
.SYNOPSIS
    Build dist/igz_sunpath.zip (the archive installed by IngeTrazo).

.DESCRIPTION
    Thin wrapper around packaging/build_extension.py.  The Python script is
    deterministic and needs only the standard library (Python 3.11+).

.EXAMPLE
    .\packaging\build_extension.ps1
    .\packaging\build_extension.ps1 -WriteCatalog
    .\packaging\build_extension.ps1 -Python "C:\Python312\python.exe"
#>
param(
    [string]$Python = "",
    [switch]$WriteCatalog,
    [switch]$Check
)

$ErrorActionPreference = "Stop"

if (-not $Python) {
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        $Python = "py"
        $prefix = @("-3")
    } else {
        $python = Get-Command python -ErrorAction SilentlyContinue
        if (-not $python) {
            throw "Python 3.11+ was not found. Pass -Python <path-to-python.exe>."
        }
        $Python = "python"
        $prefix = @()
    }
} else {
    $prefix = @()
}

$script = Join-Path $PSScriptRoot "build_extension.py"
$arguments = @()
if ($Python -eq "py") {
    $arguments += "-3"
}
$arguments += $script
if ($WriteCatalog) { $arguments += "--write-catalog" }
if ($Check) { $arguments += "--check" }

& $Python @arguments
exit $LASTEXITCODE
