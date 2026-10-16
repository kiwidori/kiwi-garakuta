package main

import (
	"bufio"
	"bytes"
	"crypto/ed25519"
	"crypto/rsa"
	"errors"
	"fmt"
	"io"
	"os"
	"strings"

	"filippo.io/age"
	"filippo.io/age/agessh"
	"filippo.io/age/armor"
	"golang.org/x/crypto/ssh"
)

const (
	maxPaths     = 16
	maxFileBytes = 1 << 20 // 1 MiB
	maxIDs       = 64
	maxRecFiles  = 16
	maxRecFile   = 64 * 1024
	maxRecTotal  = 128 * 1024
	maxPlainRead = 64 * 1024
	scryptWork   = 18
)

func readBound(path string, max int64) ([]byte, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	st, err := f.Stat()
	if err != nil {
		return nil, err
	}
	if !st.Mode().IsRegular() || st.Size() > max {
		return nil, errors.New("file too large or not regular")
	}
	b, err := io.ReadAll(io.LimitReader(f, max+1))
	if err != nil {
		return nil, err
	}
	if int64(len(b)) > max {
		return nil, errors.New("exceeds limit")
	}
	return b, nil
}

func parsePlainIdentities(b []byte, keypass string) ([]age.Identity, error) {
	t := bytes.TrimSpace(b)
	if !bytes.HasPrefix(t, []byte("-----BEGIN")) {
		return age.ParseIdentities(bytes.NewReader(b))
	}
	id, err := agessh.ParseIdentity(t)
	if err == nil {
		return []age.Identity{id}, nil
	}
	if keypass == "" {
		return nil, err
	}
	key, perr := ssh.ParseRawPrivateKeyWithPassphrase(t, []byte(keypass))
	if perr != nil {
		return nil, perr
	}
	switch kk := key.(type) {
	case *rsa.PrivateKey:
		id, err = agessh.NewRSAIdentity(kk)
	case ed25519.PrivateKey:
		id, err = agessh.NewEd25519Identity(kk)
	case *ed25519.PrivateKey:
		id, err = agessh.NewEd25519Identity(*kk)
	default:
		return nil, errors.New("unsupported key type")
	}
	if err != nil {
		return nil, err
	}
	return []age.Identity{id}, nil
}

func identities(paths []string, keypass string) ([]age.Identity, error) {
	if len(paths) > maxPaths {
		return nil, errors.New("too many paths")
	}
	var ids []age.Identity
	for _, p := range paths {
		b, err := readBound(p, maxFileBytes)
		if err != nil {
			return nil, err
		}
		t := bytes.TrimSpace(b)
		if bytes.HasPrefix(b, []byte("age-encryption.org/v1")) || bytes.HasPrefix(t, []byte("-----BEGIN AGE ENCRYPTED FILE-----")) {
			var reader io.Reader = bytes.NewReader(b)
			if bytes.HasPrefix(t, []byte("-----BEGIN AGE ENCRYPTED FILE-----")) {
				reader = bytes.NewReader(t)
			}
			r, err := decryptFrom(reader, keypass, nil)
			if err != nil {
				return nil, err
			}
			plain, err := io.ReadAll(io.LimitReader(r, maxPlainRead+1))
			if err != nil {
				return nil, err
			}
			if len(plain) > maxPlainRead {
				return nil, errors.New("decrypted data too large")
			}
			b = plain
		}
		sub, err := parsePlainIdentities(b, keypass)
		if err != nil {
			return nil, err
		}
		ids = append(ids, sub...)
		if len(ids) > maxIDs {
			return nil, errors.New("too many identities")
		}
	}
	return ids, nil
}

func recipients(lines string, files []string, fromIDs []age.Identity) ([]age.Recipient, error) {
	var recs []age.Recipient
	if len(files) > maxRecFiles {
		return nil, errors.New("too many recipient files")
	}
	var total int
	total += len(lines)
	if total > maxRecTotal {
		return nil, errors.New("recipient data too large")
	}
	for _, f := range files {
		b, err := readBound(f, maxRecFile)
		if err != nil {
			return nil, err
		}
		total += len(b)
		if total > maxRecTotal {
			return nil, errors.New("recipient data too large")
		}
		for _, line := range strings.Split(string(b), "\n") {
			line = strings.TrimSpace(line)
			if line == "" || strings.HasPrefix(line, "#") {
				continue
			}
			var r age.Recipient
			var err error
			if strings.HasPrefix(line, "ssh-") {
				r, err = agessh.ParseRecipient(line)
			} else {
				sub, perr := age.ParseRecipients(strings.NewReader(line))
				if perr != nil || len(sub) == 0 {
					return nil, errors.New("invalid recipient line")
				}
				r = sub[0]
			}
			if err != nil {
				return nil, err
			}
			recs = append(recs, r)
		}
	}
	for _, line := range strings.Split(lines, "\n") {
		line = strings.TrimSpace(line)
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		var r age.Recipient
		var err error
		if strings.HasPrefix(line, "ssh-") {
			r, err = agessh.ParseRecipient(line)
		} else {
			sub, perr := age.ParseRecipients(strings.NewReader(line))
			if perr != nil || len(sub) == 0 {
				return nil, errors.New("invalid recipient line")
			}
			r = sub[0]
		}
		if err != nil {
			return nil, err
		}
		recs = append(recs, r)
	}
	for _, id := range fromIDs {
		switch v := id.(type) {
		case *age.X25519Identity:
			recs = append(recs, v.Recipient())
		case *age.HybridIdentity:
			recs = append(recs, v.Recipient())
		case *agessh.RSAIdentity:
			recs = append(recs, v.Recipient())
		case *agessh.Ed25519Identity:
			recs = append(recs, v.Recipient())
		}
	}
	if len(recs) == 0 || len(recs) > maxIDs {
		return nil, errors.New("invalid recipient count")
	}
	return recs, nil
}

func encryptTo(out io.Writer, in io.Reader, pass string, recs []age.Recipient, textArmor bool) error {
	var finalRecs []age.Recipient
	if pass != "" {
		r, err := age.NewScryptRecipient(pass)
		if err != nil {
			return err
		}
		r.SetWorkFactor(scryptWork)
		finalRecs = append(finalRecs, r)
	} else {
		finalRecs = recs
	}
	if len(finalRecs) == 0 {
		return errors.New("no recipients")
	}
	var w io.Writer = out
	var aw io.WriteCloser
	if textArmor {
		aw = armor.NewWriter(out)
		w = aw
	}
	ew, err := age.Encrypt(w, finalRecs...)
	if err != nil {
		return err
	}
	if _, err := io.Copy(ew, in); err != nil {
		return err
	}
	if cerr := ew.Close(); cerr != nil {
		return cerr
	}
	if textArmor {
		if cerr := aw.Close(); cerr != nil {
			return cerr
		}
	}
	return nil
}

func decryptFrom(in io.Reader, pass string, ids []age.Identity) (io.Reader, error) {
	br := bufio.NewReader(in)
	prefix, err := br.Peek(10)
	if err != nil && !errors.Is(err, io.EOF) {
		return nil, err
	}
	var r io.Reader = br
	if bytes.HasPrefix(prefix, []byte("-----BEGIN")) {
		r = armor.NewReader(br)
	}
	allIDs := make([]age.Identity, 0, len(ids)+1)
	if pass != "" {
		si, err := age.NewScryptIdentity(pass)
		if err != nil {
			return nil, err
		}
		si.SetMaxWorkFactor(scryptWork)
		allIDs = append(allIDs, si)
	}
	allIDs = append(allIDs, ids...)
	out, err := age.Decrypt(r, allIDs...)
	if err != nil {
		return nil, err
	}
	return out, nil
}

func genKey(kind string) (secret, public string, err error) {
	switch kind {
	case "x25519":
		id, e := age.GenerateX25519Identity()
		if e != nil {
			return "", "", e
		}
		return id.String(), id.Recipient().String(), nil
	case "pq":
		id, e := age.GenerateHybridIdentity()
		if e != nil {
			return "", "", e
		}
		return id.String(), id.Recipient().String(), nil
	default:
		return "", "", fmt.Errorf("unknown key kind %q", kind)
	}
}
