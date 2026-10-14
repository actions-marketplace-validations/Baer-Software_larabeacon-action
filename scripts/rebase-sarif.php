<?php

// Core locations are application-relative; GitHub resolves them at repository root.
declare(strict_types=1);

$path = $argv[1];
$prefix = implode('/', array_map('rawurlencode', explode('/', $argv[2]))).'/';
$report = json_decode(file_get_contents($path), true, 512, JSON_THROW_ON_ERROR);

function rebaseLocations(array &$node, string $prefix): void
{
    foreach ($node as $key => &$value) {
        if (!is_array($value)) {
            continue;
        }
        if ($key === 'artifactLocation' && isset($value['uri'])
            && !isset($value['uriBaseId'])
            && !preg_match('~^(?:[a-zA-Z][a-zA-Z0-9+.-]*:|/|\\\\)~', $value['uri'])) {
            $value['uri'] = $prefix.$value['uri'];
        } else {
            rebaseLocations($value, $prefix);
        }
    }
}

rebaseLocations($report, $prefix);
if (file_put_contents($path, json_encode($report, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES | JSON_THROW_ON_ERROR)."\n") === false) {
    throw new RuntimeException('Could not normalize SARIF locations.');
}
