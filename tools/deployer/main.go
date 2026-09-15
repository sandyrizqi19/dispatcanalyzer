package main

import (
	"bufio"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"net/url"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"sync"
)

type Config struct {
	TargetDirectory string `json:"target_directory"`
	UpstreamURL     string `json:"upstream_url"`
	OriginURL       string `json:"origin_url"`
	GitUsername     string `json:"git_username"`
	GitToken        string `json:"git_token"`
}

var (
	configFilePath = ".deployer_config.json"
	configMutex    sync.Mutex
	isDeploying    bool
	deployMutex    sync.Mutex
)

func main() {
	mux := http.NewServeMux()

	mux.HandleFunc("/", serveIndex)
	mux.HandleFunc("/api/config", handleConfig)
	mux.HandleFunc("/api/deploy", handleDeploy)

	// Apply Basic Auth Middleware
	handler := basicAuthMiddleware(mux)

	port := "8083"
	log.Printf("Starting Deployer Manager on port %s...\n", port)
	if err := http.ListenAndServe(":"+port, handler); err != nil {
		log.Fatalf("Failed to start server: %v", err)
	}
}

func basicAuthMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		user, pass, ok := r.BasicAuth()
		if !ok || user != "deployer" || pass != "Cilandak26#" {
			w.Header().Set("WWW-Authenticate", `Basic realm="restricted", charset="UTF-8"`)
			http.Error(w, "Unauthorized", http.StatusUnauthorized)
			return
		}
		next.ServeHTTP(w, r)
	})
}

func serveIndex(w http.ResponseWriter, r *http.Request) {
	if r.URL.Path != "/" {
		http.NotFound(w, r)
		return
	}
	http.ServeFile(w, r, "index.html")
}

func loadConfig() Config {
	configMutex.Lock()
	defer configMutex.Unlock()

	var cfg Config
	data, err := os.ReadFile(configFilePath)
	if err == nil {
		json.Unmarshal(data, &cfg)
	}
	
	if cfg.TargetDirectory == "" {
		// default to parent directory
		cwd, err := os.Getwd()
		if err == nil {
			parentDir := filepath.Dir(filepath.Dir(cwd))
			cfg.TargetDirectory = parentDir
		}
	}
	return cfg
}

func saveConfig(cfg Config) error {
	configMutex.Lock()
	defer configMutex.Unlock()

	data, err := json.MarshalIndent(cfg, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(configFilePath, data, 0600)
}

func handleConfig(w http.ResponseWriter, r *http.Request) {
	if r.Method == http.MethodGet {
		cfg := loadConfig()
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(cfg)
		return
	}

	if r.Method == http.MethodPost {
		var cfg Config
		if err := json.NewDecoder(r.Body).Decode(&cfg); err != nil {
			http.Error(w, "Invalid payload", http.StatusBadRequest)
			return
		}
		if err := saveConfig(cfg); err != nil {
			http.Error(w, "Failed to save config", http.StatusInternalServerError)
			return
		}
		w.WriteHeader(http.StatusOK)
		return
	}

	http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
}

func sendSSEMessage(w http.ResponseWriter, flusher http.Flusher, msgType, text string) {
	data := map[string]string{"type": msgType, "text": text}
	payload, _ := json.Marshal(data)
	fmt.Fprintf(w, "data: %s\n\n", payload)
	flusher.Flush()
}

func handleDeploy(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	w.Header().Set("Content-Type", "text/event-stream")
	w.Header().Set("Cache-Control", "no-cache")
	w.Header().Set("Connection", "keep-alive")
	
	flusher, ok := w.(http.Flusher)
	if !ok {
		http.Error(w, "Streaming unsupported", http.StatusInternalServerError)
		return
	}

	deployMutex.Lock()
	if isDeploying {
		deployMutex.Unlock()
		fmt.Fprintf(w, "event: error_msg\ndata: {\"text\": \"Deployment is already in progress.\"}\n\n")
		flusher.Flush()
		return
	}
	isDeploying = true
	deployMutex.Unlock()

	defer func() {
		deployMutex.Lock()
		isDeploying = false
		deployMutex.Unlock()
	}()

	cfg := loadConfig()
	if cfg.TargetDirectory == "" {
		fmt.Fprintf(w, "event: error_msg\ndata: {\"text\": \"Target directory is not configured.\"}\n\n")
		flusher.Flush()
		return
	}

	sendSSEMessage(w, flusher, "info", "Starting deployment sequence in: " + cfg.TargetDirectory)

	// Prepare git remote commands
	// Inject auth into origin URL if both are provided
	originURL := cfg.OriginURL
	if cfg.GitUsername != "" && cfg.GitToken != "" && originURL != "" {
		u, err := url.Parse(originURL)
		if err == nil {
			u.User = url.UserPassword(cfg.GitUsername, cfg.GitToken)
			originURL = u.String()
		}
	}

	commands := [][]string{
		{"git", "remote", "remove", "upstream"},
		{"git", "remote", "add", "upstream", cfg.UpstreamURL},
		{"git", "remote", "remove", "origin"},
		{"git", "remote", "add", "origin", originURL},
		{"git", "fetch", "upstream"},
		{"git", "checkout", "main"},
		{"git", "merge", "upstream/main"},
		{"git", "push", "origin", "main"},
		{"docker", "compose", "down"},
		{"docker", "compose", "up", "--build", "-d"},
	}

	for _, cmdArgs := range commands {
		// skip empty remote commands if not configured
		if cmdArgs[0] == "git" && cmdArgs[1] == "remote" && cmdArgs[2] == "add" && len(cmdArgs) > 4 && cmdArgs[4] == "" {
			continue
		}

		displayArgs := append([]string(nil), cmdArgs...)
		// Mask token in output
		if len(displayArgs) > 4 && strings.Contains(displayArgs[4], cfg.GitToken) && cfg.GitToken != "" {
			displayArgs[4] = strings.ReplaceAll(displayArgs[4], cfg.GitToken, "********")
		}

		sendSSEMessage(w, flusher, "command", fmt.Sprintf("$ %s", strings.Join(displayArgs, " ")))

		cmd := exec.Command(cmdArgs[0], cmdArgs[1:]...)
		cmd.Dir = cfg.TargetDirectory

		// Git might complain about remote remove if it doesn't exist, we can ignore errors for 'remote remove'
		ignoreError := (cmdArgs[0] == "git" && cmdArgs[1] == "remote" && cmdArgs[2] == "remove")

		stderr, _ := cmd.StderrPipe()
		stdout, _ := cmd.StdoutPipe()

		if err := cmd.Start(); err != nil {
			sendSSEMessage(w, flusher, "error", fmt.Sprintf("Failed to start command: %v", err))
			if !ignoreError {
				fmt.Fprintf(w, "event: error_msg\ndata: {\"text\": \"Command execution failed.\"}\n\n")
				flusher.Flush()
				return
			}
		}

		var wg sync.WaitGroup
		wg.Add(2)

		streamOutput := func(reader io.Reader, msgType string) {
			defer wg.Done()
			scanner := bufio.NewScanner(reader)
			for scanner.Scan() {
				sendSSEMessage(w, flusher, msgType, scanner.Text())
			}
		}

		go streamOutput(stdout, "")
		go streamOutput(stderr, "") // often git writes to stderr

		wg.Wait()
		err := cmd.Wait()

		if err != nil && !ignoreError {
			sendSSEMessage(w, flusher, "error", fmt.Sprintf("Command exited with error: %v", err))
			fmt.Fprintf(w, "event: error_msg\ndata: {\"text\": \"Deployment aborted due to error.\"}\n\n")
			flusher.Flush()
			return
		}
	}

	// Done
	fmt.Fprintf(w, "event: done\ndata: {}\n\n")
	flusher.Flush()
}
