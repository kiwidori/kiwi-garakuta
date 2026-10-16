// Bounded file operations for the local age bridge.
package main

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
	"unicode/utf8"

	"filippo.io/age"
)

const plainLimit int64 = 512 << 20
const cipherLimit int64 = 768 << 20

type request struct {
	Op             string   `json:"op"`
	Input          string   `json:"input"`
	Output         string   `json:"output"`
	Password       string   `json:"password"`
	KeyPassword    string   `json:"key_password"`
	Recipients     string   `json:"recipients"`
	RecipientFiles []string `json:"recipient_files"`
	IdentityFiles  []string `json:"identity_files"`
	ToIdentity     bool     `json:"to_identity"`
	Armor          bool     `json:"armor"`
	KeyKind        string   `json:"key_kind"`
	ProtectKey     bool     `json:"protect_key"`
}
type response struct {
	OK     bool   `json:"ok"`
	Error  string `json:"error,omitempty"`
	Size   int64  `json:"size"`
	SHA256 string `json:"sha256,omitempty"`
	Public string `json:"public,omitempty"`
}

var failure = errors.New("operation_failed")

func validPassword(s string, minimum int) bool {
	return utf8.ValidString(s) && len(s) <= 1024 && utf8.RuneCountInString(s) >= minimum
}
func publicKeys(ids []age.Identity) (string, error) {
	recs, err := recipients("", nil, ids)
	if err != nil {
		return "", failure
	}
	lines := make([]string, 0, len(recs))
	for _, r := range recs {
		s, ok := r.(fmt.Stringer)
		if !ok {
			return "", failure
		}
		lines = append(lines, s.String())
	}
	return strings.Join(lines, "\n"), nil
}
func run(r request) (res response, err error) {
	if len(r.Password) > 1024 || len(r.KeyPassword) > 1024 || !utf8.ValidString(r.Password) || !utf8.ValidString(r.KeyPassword) || len(r.IdentityFiles) > 16 || len(r.RecipientFiles) > 16 || len(r.Recipients) > 128<<10 {
		return res, failure
	}
	if r.Op != "encrypt" && r.Op != "decrypt" && r.Op != "keygen" && r.Op != "public" {
		return res, failure
	}
	var ids []age.Identity
	if len(r.IdentityFiles) > 0 {
		ids, err = identities(r.IdentityFiles, r.KeyPassword)
		if err != nil {
			return res, failure
		}
	}
	if r.Op == "public" {
		res.Public, err = publicKeys(ids)
		res.OK = err == nil
		return res, err
	}
	if !filepath.IsAbs(r.Output) {
		return res, failure
	}
	var in *os.File
	var original os.FileInfo
	if r.Op != "keygen" {
		if !filepath.IsAbs(r.Input) || strings.EqualFold(filepath.Clean(r.Input), filepath.Clean(r.Output)) {
			return res, failure
		}
		in, err = os.Open(r.Input)
		if err != nil {
			return res, failure
		}
		defer in.Close()
		original, err = in.Stat()
		limit := plainLimit
		if r.Op == "decrypt" {
			limit = cipherLimit
		}
		if err != nil || !original.Mode().IsRegular() || original.Size() > limit {
			return res, failure
		}
	}
	var recs []age.Recipient
	if r.Op == "encrypt" {
		if r.Password != "" {
			if !validPassword(r.Password, 12) || r.Recipients != "" || len(r.RecipientFiles) > 0 || r.ToIdentity {
				return res, failure
			}
		} else {
			var from []age.Identity
			if r.ToIdentity {
				from = ids
			}
			recs, err = recipients(r.Recipients, r.RecipientFiles, from)
			if err != nil {
				return res, failure
			}
		}
	}
	if r.Op == "decrypt" && r.Password == "" && len(ids) == 0 {
		return res, failure
	}
	if r.Op == "keygen" && r.ProtectKey && !validPassword(r.Password, 12) {
		return res, failure
	}
	out, err := os.OpenFile(r.Output, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0600)
	if err != nil {
		return res, errors.New("output_unavailable")
	}
	complete := false
	closed := false
	defer func() {
		if !closed {
			out.Close()
		}
		if !complete {
			os.Remove(r.Output)
		}
	}()
	hash := sha256.New()
	switch r.Op {
	case "encrypt":
		err = encryptTo(out, io.TeeReader(io.LimitReader(in, plainLimit+1), hash), r.Password, recs, r.Armor)
	case "decrypt":
		var reader io.Reader
		reader, err = decryptFrom(in, r.Password, ids)
		if err == nil {
			var n int64
			n, err = io.Copy(io.MultiWriter(out, hash), io.LimitReader(reader, plainLimit+1))
			if n > plainLimit {
				err = failure
			}
		}
	case "keygen":
		var secret string
		secret, res.Public, err = genKey(r.KeyKind)
		if err == nil {
			text := "# public key: " + res.Public + "\n" + secret + "\n"
			if r.ProtectKey {
				err = encryptTo(out, strings.NewReader(text), r.Password, nil, true)
			} else {
				_, err = io.WriteString(out, text)
			}
		}
	}
	if err != nil {
		return res, failure
	}
	if in != nil {
		current, e := in.Stat()
		if e != nil || current.Size() != original.Size() || !current.ModTime().Equal(original.ModTime()) {
			return res, failure
		}
	}
	if err = out.Sync(); err != nil {
		return res, failure
	}
	err = out.Close()
	closed = true
	if err != nil {
		return res, failure
	}
	if r.Op == "encrypt" && r.Password != "" {
		check, e := os.Open(r.Output)
		if e != nil {
			return res, failure
		}
		defer check.Close()
		reader, e := decryptFrom(check, r.Password, nil)
		if e != nil {
			return res, failure
		}
		h := sha256.New()
		n, e := io.Copy(h, io.LimitReader(reader, plainLimit+1))
		if e != nil || n != original.Size() || !bytes.Equal(h.Sum(nil), hash.Sum(nil)) {
			return res, failure
		}
	}
	stat, e := os.Stat(r.Output)
	if e != nil {
		return res, failure
	}
	res.Size = stat.Size()
	if in != nil {
		res.SHA256 = hex.EncodeToString(hash.Sum(nil))
	}
	res.OK = true
	complete = true
	return res, nil
}
func main() {
	res := response{Error: "invalid_request"}
	defer func() {
		if recover() != nil {
			json.NewEncoder(os.Stdout).Encode(response{Error: "operation_failed"})
		}
	}()
	raw, err := io.ReadAll(io.LimitReader(os.Stdin, (2<<20)+1))
	if err != nil || len(raw) > 2<<20 {
		json.NewEncoder(os.Stdout).Encode(res)
		return
	}
	d := json.NewDecoder(bytes.NewReader(raw))
	d.DisallowUnknownFields()
	var r request
	if d.Decode(&r) != nil {
		json.NewEncoder(os.Stdout).Encode(res)
		return
	}
	var extra any
	if d.Decode(&extra) != io.EOF {
		json.NewEncoder(os.Stdout).Encode(res)
		return
	}
	res, err = run(r)
	if err != nil {
		res = response{Error: err.Error()}
		if res.Error != "output_unavailable" {
			res.Error = "operation_failed"
		}
	}
	json.NewEncoder(os.Stdout).Encode(res)
}
