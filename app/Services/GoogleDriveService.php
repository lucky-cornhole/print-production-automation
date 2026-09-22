<?php

namespace App\Services;

use Google\Client;
use Google\Service\Drive;
use RuntimeException;

class GoogleDriveService
{
    private Drive $drive;
    private string $rootId;
    private array $allowedFolders;

    public function __construct()
    {
        $credentials = config(
            'services.google_drive.service_account_file'
        );

        $this->rootId = trim(
            (string) config(
                'services.google_drive.artwork_root_id'
            )
        );

        $this->allowedFolders = config(
            'services.google_drive.allowed_root_folders',
            []
        );

        if (!$credentials || !file_exists($credentials)) {
            throw new RuntimeException(
                'Google service account file not found: ' .
                $credentials
            );
        }

        if ($this->rootId === '') {
            throw new RuntimeException(
                'Google Drive artwork root is not configured.'
            );
        }

        $client = new Client();

        $client->setAuthConfig($credentials);

        $client->setScopes([
            Drive::DRIVE_READONLY,
        ]);

        $this->drive = new Drive($client);
    }

    /**
     * List direct children of a Drive folder.
     */
    public function listChildren(string $folderId): array
    {
        $files = [];
        $pageToken = null;

        do {
            $response = $this->drive->files->listFiles([
                'q' =>
                    sprintf(
                        "'%s' in parents and trashed = false",
                        addslashes($folderId)
                    ),

                'fields' =>
                    'nextPageToken,files(' .
                    'id,name,mimeType,parents,' .
                    'webViewLink,imageMediaMetadata' .
                    ')',

                'pageSize' => 1000,

                'pageToken' => $pageToken,

                'supportsAllDrives' => true,

                'includeItemsFromAllDrives' => true,
            ]);

            foreach ($response->getFiles() as $file) {
                $metadata = $file->getImageMediaMetadata();

                $files[] = [
                    'id' => $file->getId(),
                    'name' => $file->getName(),
                    'mimeType' => $file->getMimeType(),
                    'webViewLink' => $file->getWebViewLink(),

                    'width' =>
                        $metadata
                            ? $metadata->getWidth()
                            : null,

                    'height' =>
                        $metadata
                            ? $metadata->getHeight()
                            : null,
                ];
            }

            $pageToken = $response->getNextPageToken();

        } while ($pageToken);

        return $files;
    }

    /**
     * Return only the approved manufacturing
     * branches underneath "2027 Bags".
     */
    public function manufacturingRoots(): array
    {
        return collect(
            $this->listChildren($this->rootId)
        )
            ->filter(
                fn (array $file) =>
                    $file['mimeType']
                        === 'application/vnd.google-apps.folder'
                    &&
                    in_array(
                        $file['name'],
                        $this->allowedFolders,
                        true
                    )
            )
            ->values()
            ->all();
    }

    /**
     * Recursively index all artwork underneath
     * Group A and Group B.
     */
    public function artworkIndex(): array
    {
        $results = [];

        foreach ($this->manufacturingRoots() as $root) {
            $this->walkFolder(
                $root['id'],
                $root['name'],
                $results
            );
        }

        return $results;
    }

    private function walkFolder(
        string $folderId,
        string $path,
        array &$results
    ): void {
        foreach (
            $this->listChildren($folderId)
            as $file
        ) {
            $currentPath =
                $path . '/' . $file['name'];

            if (
                $file['mimeType']
                === 'application/vnd.google-apps.folder'
            ) {
                $this->walkFolder(
                    $file['id'],
                    $currentPath,
                    $results
                );

                continue;
            }

            /*
             * Manufacturing artwork only.
             */
            $extension = strtolower(
                pathinfo(
                    $file['name'],
                    PATHINFO_EXTENSION
                )
            );

            if (!in_array(
                $extension,
                [
                    'jpg',
                    'jpeg',
                    'png',
                    'tif',
                    'tiff',
                    'webp',
                    'psd',
                    'pdf',
                ],
                true
            )) {
                continue;
            }

            $results[] = [
                'id' => $file['id'],
                'name' => $file['name'],
                'path' => $currentPath,
                'webViewLink' =>
                    $file['webViewLink'],

                'width' => $file['width'],
                'height' => $file['height'],
            ];
        }
    }
}